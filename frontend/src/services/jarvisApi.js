const API_BASE = import.meta.env.VITE_API_URL ?? ''

function formatApiError(payload, fallback) {
  const detail = payload?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg
  return fallback
}

export async function checkBackendHealth() {
  const response = await fetch(`${API_BASE}/api/health`)
  if (!response.ok) {
    throw new Error('Backend is not reachable')
  }
  return response.json()
}

export async function sendVoiceTurn(audioBlob, history = []) {
  const formData = new FormData()
  formData.append('audio', audioBlob, 'speech.webm')
  formData.append('history', JSON.stringify(history))

  const response = await fetch(`${API_BASE}/api/voice-turn`, {
    method: 'POST',
    body: formData,
  })

  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(formatApiError(payload, 'Voice request failed'))
  }

  return payload
}

function decodeBase64Audio(audioBase64) {
  const binary = atob(audioBase64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes.buffer
}

export async function playBase64Audio(audioBase64, mimeType, audioContext) {
  if (!audioContext) {
    throw new Error('Audio is not ready. Click Enable voice first.')
  }

  if (audioContext.state === 'suspended') {
    await audioContext.resume()
  }

  const bytes = decodeBase64Audio(audioBase64)

  try {
    const audioBuffer = await audioContext.decodeAudioData(bytes.slice(0))
    const source = audioContext.createBufferSource()
    source.buffer = audioBuffer
    source.connect(audioContext.destination)

    return new Promise((resolve, reject) => {
      source.onended = () => resolve()
      try {
        source.start(0)
      } catch (error) {
        reject(error)
      }
    })
  } catch {
    return playWithHtmlAudio(audioBase64, mimeType, audioContext)
  }
}

async function playWithHtmlAudio(audioBase64, mimeType, audioContext) {
  if (audioContext.state === 'suspended') {
    await audioContext.resume()
  }

  const audio = new Audio(`data:${mimeType};base64,${audioBase64}`)

  try {
    await audio.play()
  } catch (error) {
    if (error?.name === 'NotAllowedError') {
      throw new Error(
        'Speech playback blocked. Click Enable voice on the page, then try again.',
        { cause: error },
      )
    }
    throw error
  }

  return new Promise((resolve, reject) => {
    audio.onended = () => resolve()
    audio.onerror = () => reject(new Error('Failed to play J.A.R.V.I.S. voice'))
  })
}

export function getMediaErrorMessage(error) {
  const name = error?.name ?? ''
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
    return 'Microphone access denied. Allow the mic in browser settings, then click Enable voice again.'
  }
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return 'No microphone found. Connect a mic and try again.'
  }
  if (name === 'NotReadableError' || name === 'TrackStartError') {
    return 'Microphone is in use by another app. Close other apps using the mic and try again.'
  }
  if (error instanceof Error && error.message) {
    return error.message
  }
  return 'Could not access the microphone.'
}
