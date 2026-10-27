import type { Params } from './params'

export interface TrackInfo {
  id: string
  name: string
  title: string
  duration: number
}

async function errorText(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') return body.detail
    return JSON.stringify(body.detail ?? body)
  } catch {
    return `${res.status} ${res.statusText}`
  }
}

export async function uploadTrack(file: File): Promise<TrackInfo> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch('/api/upload', { method: 'POST', body: form })
  if (!res.ok) throw new Error(await errorText(res))
  return res.json()
}

export async function renderSvg(id: string, params: Params, signal: AbortSignal): Promise<string> {
  const res = await fetch('/api/render', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id, params }),
    signal,
  })
  if (!res.ok) throw new Error(await errorText(res))
  return res.text()
}
