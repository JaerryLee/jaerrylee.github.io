---
title: "LLM 서빙 성능 읽기: TTFT·KV 캐시·배칭·양자화"
description: "첫 토큰 지연과 생성 속도를 구분하고 메모리·스케줄링·커널 최적화를 실제 부하에서 비교하는 기준."
date: 2026-09-28
category: LLM Ops
tags: [Inference, vLLM, TTFT, KV Cache, Quantization]
order: 4
---

“초당 토큰 수가 높다”는 설명만으로 서비스가 빠른지 판단하기 어렵다. 한 사용자의 생성 속도인지 서버 전체 처리량인지, 얼마나 기다린 뒤 응답을 받는지에 따라 의미가 달라진다. 서빙 최적화는 **측정 범위와 부하를 고정한 뒤 병목에 맞는 기술을 고르는 일**에서 시작한다.

이 글은 원 논문과 공식 문서를 정리한 성능 분석 노트다. 아래 계산 예시는 가정에 따른 산술이며 특정 서버에서 측정한 벤치마크가 아니다.

## Prefill과 decode를 나누어 보기

Prefill은 알려진 입력 토큰을 처리해 KV 캐시와 첫 출력의 분포를 만드는 단계다. Decode는 이미 생성한 토큰에 이어 다음 토큰을 반복 생성한다. 일반적으로 prefill은 큰 행렬 연산을 활용하기 쉽고 작은 배치의 decode는 메모리 대역폭의 영향을 많이 받지만, 모델 구조·문맥 길이·배치·하드웨어에 따라 병목은 달라진다.

| 지표 | 의미 | 함께 기록할 조건 |
| --- | --- | --- |
| TTFT | 요청 시작부터 첫 출력 토큰까지 | 클라이언트/서버 기준, 큐·검색·네트워크 포함 여부 |
| ITL | 연속 출력 토큰 사이의 지연 | 토큰과 스트리밍 청크의 차이, 긴 멈춤 |
| TPOT | 요청별 첫 토큰 이후의 평균 토큰 시간 | 계산 정의, 출력 토큰 수 |
| E2E latency | 요청 시작부터 완료까지 | 출력 길이, 취소·오류 처리 |
| Throughput | 구간당 완료 요청 또는 생성 토큰 수 | 서버 전체/요청별, 입력/출력 토큰 구분 |

출력 토큰을 하나씩 관측했고 `N > 1`이면 요청별 평균 TPOT를 `(마지막 토큰 시각 − 첫 토큰 시각) / (N − 1)`로 계산할 수 있다. 여러 토큰을 한 청크로 받았다면 청크 간격을 실제 ITL로 부르면 안 된다. p95 같은 백분위도 요청별 TPOT 분포인지 모든 토큰 간격의 분포인지 명시한다. vLLM은 서버 관측용 메트릭을 `/metrics`로 제공하며, 실제 이름과 제공 범위는 실행 버전에서 확인한다. [vLLM Production Metrics](https://docs.vllm.ai/en/stable/usage/metrics/)

## GPU 메모리는 가중치만 계산하면 부족하다

일반적인 full-attention decoder에서 모든 레이어의 KV head 수와 head 차원이 같고 캐시를 공유하지 않는다고 가정하면 다음 근사식을 쓸 수 있다.

```text
KV bytes ≈ 2 × layers × kv_heads × head_dim
           × bytes_per_element × Σ(cached_tokens_per_sequence)
```

앞의 2는 key와 value다. 예를 들어 32 layers, 8 KV heads, head dimension 128, BF16 2 bytes이면 토큰당 KV는 `131,072 bytes = 128 KiB`다. 8,192토큰 시퀀스 하나는 약 1 GiB, 이를 공유 없이 16개 유지하면 약 16 GiB다. 여기에 가중치, activation·workspace, CUDA graph 등 런타임 메모리가 더 필요하다.

GQA는 여러 query head가 더 적은 KV head를 사용하게 하므로 캐시 계산에 query head 수를 그대로 넣으면 과대평가한다. MQA는 KV head 하나를 쓰는 경우다. 이는 모델 구조와 관련된 선택이며 기존 모델의 실행 옵션 하나를 바꿔 항상 얻을 수 있는 효과는 아니다. [GQA 논문](https://arxiv.org/abs/2305.13245)

위 식은 레이어별 구조 차이, sliding window, MLA·하이브리드 구조, 캐시 공유·양자화 메타데이터까지 표현하지 않는다. 용량 계획의 시작점으로 사용하고 실행 엔진의 실제 할당량으로 확인한다. 메모리 단편화와 블록 관리는 [PagedAttention 글](/posts/pagedattention-memory-management/)에서 별도로 다룬다.

## 배칭과 스케줄링은 처리량과 대기를 함께 바꾼다

고정 배치는 묶인 요청을 함께 처리한다. continuous batching은 생성 반복 사이에 끝난 요청을 빼고 새 요청을 넣어 자원을 재사용한다. 동시 요청을 늘리면 처리량이 개선될 수 있지만, 큐 대기와 KV 캐시 압박 때문에 개별 지연은 나빠질 수 있다.

Chunked prefill은 긴 입력 처리를 나눠 decode와 함께 스케줄한다. vLLM의 튜닝 문서는 토큰 예산이 TTFT·ITL·처리량의 절충에 영향을 준다고 설명한다. 따라서 “배치 크기를 크게 하면 빨라진다”보다 목표 지연을 만족하는 부하 범위를 측정해야 한다. 캐시 부족으로 선점·재계산이 반복되는지도 확인한다. [vLLM 최적화 가이드](https://docs.vllm.ai/en/stable/configuration/optimization/)

실험에서는 입력·출력 길이 분포, 도착률, 동시성, warm-up, prefix cache의 cold/warm 상태를 고정한다. 성공 응답만 남기지 말고 timeout·취소·오류와 대기열 증가도 보고한다. 요청을 완료해야 다음 요청을 보내는 부하와 일정 도착률로 계속 보내는 부하는 과부하 상황을 다르게 드러낸다.

## 이름이 비슷한 최적화도 줄이는 비용이 다르다

| 기술 | 주로 줄이는 비용 | 한계·검증 지점 |
| --- | --- | --- |
| [FlashAttention](https://arxiv.org/abs/2205.14135) | 타일링으로 attention의 HBM↔SRAM 데이터 이동 감소 | KV 캐시의 수명·공유 관리와는 다른 문제 |
| PagedAttention | KV 블록의 과잉 예약·단편화·중복 저장 감소 | 개별 커널이 항상 더 빠른 것은 아님 |
| [Prefix caching](https://docs.vllm.ai/en/stable/features/automatic_prefix_caching/) | 동일한 prefix의 KV 재계산 감소 | 주로 prefill 절약, 새로운 출력의 decode는 계속 필요 |
| [Speculative decoding](https://arxiv.org/abs/2211.17192) | 여러 후보 토큰을 검증해 순차 실행 횟수 감소 | 후보 생성 비용, 채택률, 부하에 따라 이득 변화 |

Prefix cache는 답변 문자열을 재사용하는 response cache와 다르다. prefix의 토큰과 캐시 호환 조건이 맞아야 하며, 모델·adapter·문맥 등 캐시 키와 격리 정책을 확인한다. 높은 hit rate만으로 종단간 개선을 결론 내리지 말고 절약된 prefill 시간과 전체 지연을 같이 본다.

원 speculative decoding 알고리즘은 적절한 채택·보정 절차로 목표 모델의 분포를 유지한다. 작은 모델의 답을 검증 없이 내보내는 방식과 다르며, 모든 구현·근사 옵션이 같은 보장을 갖는다고 가정하지 않는다.

## 양자화 방식과 파일 형식 구분하기

양자화는 가중치·activation·KV 캐시 중 무엇의 정밀도를 줄이는지부터 구분한다. 가중치가 4비트라고 KV 캐시도 자동으로 4비트가 되는 것은 아니다. 메타데이터·scale·일시 버퍼도 있어 전체 VRAM이 비트 수에 정확히 비례하지 않는다.

[GPTQ](https://arxiv.org/abs/2210.17323)와 [AWQ](https://arxiv.org/abs/2306.00978)는 학습 후 가중치 양자화 방법이다. [GGUF](https://github.com/ggml-org/ggml/blob/master/docs/gguf.md)는 모델 텐서와 메타데이터를 담는 파일 형식이므로 세 가지를 동급 알고리즘으로 비교하면 부정확하다. GGUF 안에 어떤 양자화 표현을 담았는지와 실행 엔진의 지원을 따로 확인한다.

저정밀 모델이 더 작아도 대상 GPU의 커널 지원이나 변환 비용 때문에 항상 더 빠르지는 않다. 같은 데이터로 품질을 평가하고, 같은 부하에서 TTFT·생성 속도·처리량·메모리를 비교한다. 엔진의 지원 모델·하드웨어 표와 실제 실행 버전을 기준으로 판단한다. [vLLM 양자화 지원](https://docs.vllm.ai/en/stable/features/quantization/)

## 병렬화와 호스팅은 운영 비용까지 비교하기

Tensor parallelism은 레이어 내부 연산을, pipeline parallelism은 레이어 구간을 여러 장치에 나눈다. Data parallelism은 서빙 replica를 늘려 서로 다른 요청을 처리한다. 모델 분할은 장치 간 통신과 동기화를 추가하고, replica 확장은 각각의 가중치·캐시와 라우팅이 필요하다. GPU 수만으로 선형 가속을 기대하지 않는다.

외부 API는 GPU 운영 부담을 줄이지만 제공자의 한도와 지연·버전 정책을 관리해야 한다. 자체 호스팅은 모델·런타임을 통제하는 대신 idle 비용, 용량 계획, 장애 대응이 생긴다. 하이브리드 라우팅은 품질·데이터 처리 범위·fallback 조건을 함께 평가한다.

최종 비교표에는 품질, 목표 지연 안에서 처리한 요청 수, 실패율, 실제 비용을 함께 둔다. 캐시나 작은 모델로 비용을 낮춰도 작업을 성공시키지 못한다면 같은 서비스를 더 싸게 운영한 것으로 볼 수 없다. 이 결과를 [출시 게이트](/posts/llmops-operating-loop/)에 연결한다.
