import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import App from './App'

describe('App', () => {
  it('names the product and the three services', () => {
    render(<App />)

    expect(screen.getByRole('heading', { level: 1, name: 'WebChat' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Identity' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Social' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Chat' })).toBeInTheDocument()
  })
})
