import rss from '@astrojs/rss'
import type { APIContext } from 'astro'
import { getPosts } from '../lib/posts'

export async function GET(context: APIContext) {
  const posts = await getPosts()
  return rss({
    title: '이정재의 엔지니어링 노트',
    description: 'Applied AI, LLM Ops와 백엔드 설계의 구현 경험',
    site: context.site!,
    items: posts.map(post => ({
      title: post.data.title,
      description: post.data.description,
      pubDate: post.data.date,
      link: `/posts/${post.id}/`,
    })),
    customData: '<language>ko-kr</language>',
  })
}
