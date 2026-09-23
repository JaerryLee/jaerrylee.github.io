import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'

const root = fileURLToPath(new URL('../', import.meta.url))
const read = path => readFileSync(resolve(root, path), 'utf8')
const papers = JSON.parse(read('src/data/papers.json'))
const topics = JSON.parse(read('src/data/paper-topics.json'))
const ids = new Set(papers.map(paper => paper.id))
const errors = []
const check = (condition, message) => { if (!condition) errors.push(message) }
const topicIds = new Set(topics.map(topic => topic.id))
const classified = topics.flatMap(topic => topic.papers)

check(ids.size === papers.length, 'Duplicate paper IDs')
check(new Set(classified).size === classified.length, 'Paper belongs to multiple topics')
check(classified.length === papers.length && classified.every(id => ids.has(id)), 'Topic catalog and papers differ')

for (const topic of topics) {
  for (const id of topic.starters) {
    check(topic.papers.includes(id) && ids.has(id), `Invalid reading-path entry: ${topic.id}/${id}`)
  }
}

let figures = 0
for (const paper of papers) {
  check(/^[a-z0-9.-]+$/.test(paper.id), `Invalid paper ID: ${paper.id}`)
  check(topicIds.has(paper.topic), `Unknown topic: ${paper.id}`)
  check(topics.find(topic => topic.id === paper.topic)?.papers.includes(paper.id), `Incorrect classification: ${paper.id}`)
  check(Boolean(paper.title && paper.originalTitle && paper.summary && paper.intro), `Incomplete metadata: ${paper.id}`)
  check(/^https:\/\//.test(paper.sourceUrl), `Missing public source: ${paper.id}`)
  check(!paper.pdfUrl || /^https:\/\//.test(paper.pdfUrl), `Invalid PDF source: ${paper.id}`)
  check(/^\d{4}-\d{2}-\d{2}$/.test(paper.collectedOn) && !Number.isNaN(Date.parse(paper.collectedOn)), `Invalid date: ${paper.id}`)
  const path = `src/content/papers/${paper.id}.html`
  if (!existsSync(resolve(root, path))) {
    errors.push(`Missing explanation: ${paper.id}`)
    continue
  }
  const html = read(path)
  check(!/<(?:script|style|iframe|object|embed|form|input)\b/i.test(html), `Active HTML: ${paper.id}`)
  check(!/\s(?:on[a-z]+|style)\s*=/i.test(html), `Active HTML attribute: ${paper.id}`)
  const anchors = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]))
  check(paper.headings.length > 0, `Missing table of contents: ${paper.id}`)
  for (const heading of paper.headings) check(anchors.has(heading.id), `Broken heading: ${paper.id}#${heading.id}`)
  for (const [, href] of html.matchAll(/\bhref="([^"]+)"/g)) {
    check(href.startsWith('https://') || (href.startsWith('#') && anchors.has(href.slice(1))), `Broken body link: ${paper.id}: ${href}`)
  }
  for (const [, src] of html.matchAll(/\bsrc="([^"]+)"/g)) {
    check(/^\/paper-assets\/[a-f0-9]{64}\.(png|jpg|webp|gif|svg)$/.test(src) && existsSync(resolve(root, `public${src}`)), `Missing figure: ${paper.id}: ${src}`)
    figures++
  }
}

if (errors.length) throw new Error(errors.join('\n'))
console.log(`Paper content checked: ${papers.length} notes, ${topics.length} topics, ${figures} figure references.`)
