import { getCollection } from 'astro:content'

export async function getPosts() {
  return (await getCollection('posts', ({ data }) => !data.draft))
    .sort((a, b) => b.data.date.valueOf() - a.data.date.valueOf() || a.data.order - b.data.order)
}

export function formatDate(date: Date) {
  return date.toISOString().slice(0, 10).replaceAll('-', '.')
}
