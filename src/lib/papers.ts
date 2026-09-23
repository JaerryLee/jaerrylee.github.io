import records from '../data/papers.json'
import topics from '../data/paper-topics.json'

export const paperTopics = topics
export const papers = records
export type Paper = (typeof papers)[number]

const bodies = import.meta.glob<string>('../content/papers/*.html', {
  query: '?raw',
  import: 'default',
  eager: true,
})

export function getPaper(id: string) {
  const paper = papers.find(item => item.id === id)
  if (!paper) throw new Error(`Unknown paper: ${id}`)
  return paper
}

export function getPaperBody(id: string) {
  const body = bodies[`../content/papers/${id}.html`]
  if (!body) throw new Error(`Missing paper explanation: ${id}`)
  return body
}

export function getPaperTopic(id: string) {
  const topic = paperTopics.find(item => item.id === id)
  if (!topic) throw new Error(`Unknown paper topic: ${id}`)
  return topic
}
