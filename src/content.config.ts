import { defineCollection } from 'astro:content'
import { glob } from 'astro/loaders'
import { z } from 'astro/zod'

const posts = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/posts' }),
  schema: z.object({
    title: z.string(),
    description: z.string(),
    date: z.coerce.date(),
    category: z.enum(['LLM Ops', 'Applied AI', 'Backend', 'Agentic AI', 'Research Notes']),
    tags: z.array(z.string()),
    order: z.number(),
    draft: z.boolean().default(false),
  }),
})

export const collections = { posts }
