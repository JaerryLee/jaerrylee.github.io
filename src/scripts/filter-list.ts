export function filterList(noun: string) {
  const input = document.querySelector<HTMLInputElement>('#post-search')!
  const rows = [...document.querySelectorAll<HTMLElement>('[data-post]')]
  const buttons = [...document.querySelectorAll<HTMLButtonElement>('[data-filter]')]
  const status = document.querySelector<HTMLElement>('#search-status')!
  const empty = document.querySelector<HTMLElement>('#empty-state')!
  let category = 'all'

  function update() {
    const terms = input.value.normalize('NFC').trim().toLowerCase().split(/\s+/).filter(Boolean)
    let count = 0
    for (const row of rows) {
      const matches = (category === 'all' || row.dataset.category === category)
        && terms.every(term => row.dataset.search?.includes(term))
      row.hidden = !matches
      if (matches) count++
    }
    for (const button of buttons) {
      const selected = button.dataset.filter === category
      button.classList.toggle('active', selected)
      button.setAttribute('aria-pressed', String(selected))
    }
    status.textContent = `${count}${noun}`
    empty.hidden = count > 0
  }

  input.addEventListener('input', update)
  buttons.forEach(button => button.addEventListener('click', () => {
    category = button.dataset.filter!
    update()
  }))
  document.querySelector('#reset-search')?.addEventListener('click', () => {
    category = 'all'
    input.value = ''
    update()
    input.focus()
  })
}
