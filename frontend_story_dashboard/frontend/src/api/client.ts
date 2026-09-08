export class ApiError extends Error {
  constructor(public status: number | null, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function getJson<T>(path: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, { signal: AbortSignal.timeout(8000) })
  } catch (error) {
    throw new ApiError(null, error instanceof Error ? error.message : 'Network request failed')
  }
  if (!response.ok) throw new ApiError(response.status, `Request failed: ${response.status}`)
  return response.json() as Promise<T>
}
