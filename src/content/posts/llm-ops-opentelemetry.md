---
title: "LLM 실행을 따라가는 OpenTelemetry 로깅과 트레이싱"
description: "FastAPI부터 모델·도구 호출까지 요청 문맥을 연결하고, 로그·트레이스·메트릭을 수집하는 LLM Ops 구현 기록."
date: 2026-09-21
category: LLM Ops
tags: [OpenTelemetry, Pydantic AI, FastAPI, OTLP, Observability]
order: 1
---

현재는 LLM과 에이전트의 실행을 관측하는 LLM Ops 업무를 맡고 있다. 이전에 AI 기능과 백엔드를 개발했다면, 지금은 그 기능이 실제로 어떤 경로를 거쳐 실행되고 어디에서 지연되거나 실패하는지 확인할 수 있도록 연결하는 일이 중심이다.

내가 구현한 범위는 FastAPI·httpx와 Pydantic AI의 계측, 요청 문맥 전파, 표준 OpenTelemetry 로그·트레이스·메트릭의 OTLP 수집 경로, 환경별 배포 설정이다. 이 글에서는 그중 **하나의 요청을 모델과 도구 호출까지 따라가기 위한 구성**을 정리한다.

## HTTP 응답 하나로는 실행을 설명하기 어렵다

LLM 요청은 API에서 끝나지 않는다. 오케스트레이터가 실행을 만들고, 에이전트가 모델을 호출하며, 모델의 판단에 따라 도구를 실행한 뒤 다시 모델에 결과를 전달할 수 있다. 사용자에게 보이는 응답 하나 안에 여러 번의 호출과 대기가 들어간다.

이때 HTTP 상태 코드와 전체 응답 시간만 있으면 문제가 발생한 위치를 좁히기 어렵다. 모델 호출이 오래 걸렸는지, 도구가 실패했는지, 실행은 완료됐지만 전달 과정에서 문제가 생겼는지를 구분해야 한다. 내가 구성한 관측의 출발점은 이 실행 흐름을 연결하는 것이었다.

<figure class="flow-diagram">
  <ol aria-label="관측 데이터의 수집 경로"><li>API · Agent 계측</li><li>OTLP Collector</li><li>ClickHouse 저장</li><li>HyperDX 조회</li></ol>
  <figcaption>애플리케이션에서 만든 관측 데이터를 수집·저장하고, 같은 실행 문맥으로 조회하는 흐름을 단순화했다.</figcaption>
</figure>

## 세 신호의 수집 경로를 따로 구성한다

트레이스가 보인다고 해서 로그와 메트릭까지 자동으로 수집되는 것은 아니다. 애플리케이션에서는 세 신호에 각각 provider와 exporter 경로를 연결했다.

| 신호 | 애플리케이션 구성 | 확인하려는 내용 |
| --- | --- | --- |
| 트레이스 | `TracerProvider`와 `BatchSpanProcessor` | 서비스·모델·도구의 호출 관계와 실행 구간 |
| 메트릭 | `MeterProvider`와 주기적 exporter | 계측에서 제공하는 토큰 사용량, 비용, 첫 청크 지연 |
| 로그 | `LoggerProvider`와 표준 `LoggingHandler` | 실행 중 남긴 이벤트와 오류의 구체적인 설명 |

OTLP HTTP exporter는 신호에 따라 `/v1/traces`, `/v1/metrics`, `/v1/logs`로 데이터를 보낸다. 공통 resource에는 서비스 식별 정보를 넣어 서로 다른 서비스의 데이터를 구분한다. OpenTelemetry도 이 신호들을 별도의 관측 데이터로 정의한다. [OpenTelemetry Signals](https://opentelemetry.io/docs/concepts/signals/)

Pydantic AI의 내장 계측은 에이전트 실행과 모델·도구 호출을 관측하는 데 활용했다. 내가 사용한 구성에서는 에이전트 실행 아래에 모델 호출과 도구 실행 스팬이 만들어지고, 계측이 제공하는 사용량 메트릭은 설정한 meter 경로로 전달된다. 라이브러리의 기본 계측을 연결하는 역할과 애플리케이션의 로그를 만드는 역할을 분리한 것이다. [Pydantic AI 계측](https://pydantic.dev/docs/ai/integrations/logfire/)

## 호출 관계와 검색할 문맥은 따로 연결한다

서비스 사이에는 `traceparent`와 `tracestate`를 포함한 trace context가 전달되어야 한다. FastAPI의 수신 계측과 httpx의 송신 계측을 연결하고, W3C trace context와 baggage를 전파하도록 구성했다. 그래야 오케스트레이터와 코어의 호출이 서로 무관한 트레이스로 보이지 않는다. [Python 문맥 전파](https://opentelemetry.io/docs/languages/python/propagation/)

여기서 한 가지를 더 처리했다. **스팬의 부모·자식 관계가 이어진다고 부모 스팬의 모든 속성이 자식에게 복사되지는 않는다.** 요청 ID와 세션 문맥을 최상위 스팬에만 넣으면 개별 모델 호출을 직접 조회할 때 해당 실행을 식별하기 번거롭다.

그래서 요청 범위의 속성을 `ContextVar`에 보관하고, 새 스팬이 시작되는 시점에 필요한 속성을 붙이는 processor를 추가했다. 원리를 설명하는 축약 예시는 다음과 같다. 실제 exporter 설정과 HTTP 문맥 전파 코드는 생략했다.

```python
from contextlib import contextmanager
from contextvars import ContextVar
from opentelemetry.sdk.trace import SpanProcessor

request_fields: ContextVar[dict[str, str]] = ContextVar(
    "request_fields", default={}
)

@contextmanager
def request_scope(request_id: str, session_id: str):
    token = request_fields.set({
        "app.request_id": request_id,
        "app.session_id": session_id,
    })
    try:
        yield
    finally:
        request_fields.reset(token)

class RequestFieldsProcessor(SpanProcessor):
    def on_start(self, span, parent_context=None):
        span.set_attributes(request_fields.get())
```

`finally`에서 문맥을 되돌리는 부분이 중요하다. 요청이 실패하거나 중간에 취소되더라도 다음 실행에 이전 속성이 남아서는 안 된다. 실제 구현에서는 관측 속성을 추가하다 생긴 오류가 에이전트 실행을 중단시키지 않도록 처리했다.

이 방식은 현재 비동기 실행 문맥에서 생성되는 스팬에 적용된다. 큐나 별도 프로세스처럼 문맥이 끊기는 경계까지 `ContextVar`가 자동으로 따라가는 것은 아니다. 그런 경계에서는 문맥을 전달하고 복원하는 경로를 별도로 확인해야 한다.

## 로그를 실행 스팬과 연결한다

로그는 표준 Python logging에 OpenTelemetry `LoggingHandler`를 붙여 수집했다. 활성 스팬 안에서 기록한 로그를 trace ID와 span ID로 연결하면, 오류 메시지를 발견한 뒤 같은 실행의 모델·도구 호출로 이동할 수 있다.

stdout은 로컬 실행과 컨테이너의 기본 진단 경로로 유지하고, OTLP는 중앙 조회 경로로 연결했다. 초기화가 여러 번 호출될 때 handler가 중복 등록되지 않도록 재사용 여부도 처리했다.

두 경로를 모두 수집하는 환경에서는 같은 애플리케이션 로그가 서로 다른 수집 경로에서 보일 수 있다. handler 중복 등록을 막는 것과 수집 인프라의 중복 표시를 해결하는 것은 다른 문제다. 조회 시 서비스와 수집 경로를 함께 확인하도록 구분했다.

또한 stdout에 문자열 형태의 trace ID를 출력하는 일과 OTLP 로그 레코드에 trace context가 실리는 일은 별개다. 화면에서 ID가 보이는지만 확인하지 않고, 로그에서 해당 트레이스로 실제 연결되는지를 확인해야 한다.

## 관측 설정도 실행 환경의 일부다

개발 환경에서 Collector의 주소가 해석되지 않더라도 기본 로그까지 사라져서는 안 된다. 로그 초기화에는 Collector 호스트 확인과 설정 실패 처리 경로를 두고 stdout을 유지했다. 이것이 Collector의 모든 장애를 탐지하거나 로그 유실을 없앤다는 뜻은 아니다. 시작 시점의 설정 문제와 실행 중 전송 실패는 구분해야 한다.

관측 데이터의 양과 내용도 설정 대상이다. 환경별로 모델 입력·도구 인자 등의 콘텐츠 수집 옵션을 제어하고, 헬스체크처럼 반복적인 요청이 주요 실행을 가리지 않도록 제외 설정을 적용했다. 콘텐츠를 저장하지 않아도 호출 관계와 지연·오류를 볼 수 있는 구성인지 함께 살폈다.

메트릭 역시 숫자의 의미를 확인해야 한다. 첫 청크 지연은 전체 응답 완료 시간과 다르고, 계측 라이브러리가 산출한 비용은 별도 청구 내역을 대신하지 않는다. 관측 가능한 숫자와 비용 절감·성능 개선의 실측 성과를 같은 것으로 쓰지 않았다.

## 내가 확인하는 관측의 완료 조건

관측 기능은 대시보드에 데이터가 한 번 뜨는 것만으로 완료됐다고 판단하기 어렵다. 다음 질문을 실행 단위로 확인하는 것이 더 유용했다.

1. API 요청에서 시작해 모델·도구 호출까지 같은 실행을 따라갈 수 있는가?
2. 특정 오류 로그에서 관련 스팬과 요청·세션 문맥을 찾을 수 있는가?
3. 모델 사용량 메트릭과 사용자에게 보인 지연을 구분해서 설명할 수 있는가?
4. Collector가 없는 로컬 환경에서도 기본 실행과 진단이 가능한가?
5. 재초기화, 스트리밍, 요청 종료 이후에도 문맥과 수집 경로가 의도대로 유지되는가?

현재의 LLM Ops 업무에서는 이 연결을 계속 다듬고 있다. 모델 호출을 하나 추가하는 경험을 넘어, 그 호출이 제품 안에서 어떻게 실행되는지 설명할 수 있는 체계를 만드는 일이다.
