import { useCallback, useEffect, useRef, useState } from 'react'
import {
  checkBackendHealth,
  getMediaErrorMessage,
  playBase64Audio,
  sendVoiceTurn,
} from '../services/jarvisApi'

const SILENCE_MS = 900
const MIN_SPEECH_MS = 400
const SPEECH_THRESHOLD = 18
const MIN_AUDIO_BYTES = 1500

function formatTime(date = new Date()) {
  return date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function createEntry(role, text, extra = {}) {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role,
    text,
    time: formatTime(),
    ...extra,
  }
}

function getRecorderMimeType() {
  if (typeof MediaRecorder === 'undefined') return ''
  const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']
  return types.find((type) => MediaRecorder.isTypeSupported(type)) ?? ''
}

function measureVoiceLevel(analyser, frequencyData) {
  analyser.getByteFrequencyData(frequencyData)
  let sum = 0
  const end = Math.floor(frequencyData.length * 0.45)
  for (let i = 2; i < end; i += 1) {
    sum += frequencyData[i]
  }
  return sum / Math.max(end - 2, 1)
}

export function useJarvis() {
  const [entries, setEntries] = useState([])
  const [status, setStatus] = useState('checking')
  const [mediaStream, setMediaStream] = useState(null)
  const [unlockError, setUnlockError] = useState('')

  const conversationRef = useRef([])
  const isProcessingRef = useRef(false)
  const voiceUnlockedRef = useRef(false)
  const mediaStreamRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const audioContextRef = useRef(null)
  const analyserRef = useRef(null)
  const chunksRef = useRef([])
  const monitorTimerRef = useRef(null)
  const speechStartedAtRef = useRef(null)
  const silenceStartedAtRef = useRef(null)
  const speechDetectedRef = useRef(false)
  const disposedRef = useRef(false)

  const patchEntry = useCallback((id, patch) => {
    setEntries((prev) =>
      prev.map((entry) => (entry.id === id ? { ...entry, ...patch } : entry)),
    )
  }, [])

  const startRecordingCycle = useCallback(() => {
    const recorder = mediaRecorderRef.current
    if (!recorder || recorder.state === 'recording' || isProcessingRef.current) return

    chunksRef.current = []
    speechDetectedRef.current = false
    speechStartedAtRef.current = null
    silenceStartedAtRef.current = null
    recorder.start()
  }, [])

  const processRecording = useCallback(
    async (audioBlob) => {
      if (audioBlob.size < MIN_AUDIO_BYTES || isProcessingRef.current) {
        startRecordingCycle()
        return
      }

      isProcessingRef.current = true
      const assistantEntry = createEntry('assistant', '', { streaming: true })
      setEntries((prev) => [...prev, assistantEntry])
      setStatus('transcribing')

      try {
        setStatus('thinking')
        const result = await sendVoiceTurn(audioBlob, conversationRef.current)

        const reply = (result.reply || '').trim() || 'I could not generate a response.'
        if (result.transcript) {
          conversationRef.current.push({ role: 'user', content: result.transcript })
        }
        conversationRef.current.push({ role: 'assistant', content: reply })
        if (conversationRef.current.length > 24) {
          conversationRef.current = conversationRef.current.slice(-24)
        }

        patchEntry(assistantEntry.id, { text: reply, streaming: false })
        setStatus('speaking')

        if (result.audioBase64 && audioContextRef.current) {
          await playBase64Audio(
            result.audioBase64,
            result.audioMimeType || 'audio/mpeg',
            audioContextRef.current,
          )
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Backend request failed.'
        patchEntry(assistantEntry.id, {
          text: message,
          streaming: false,
          role: 'error',
        })
        setStatus('error')
      } finally {
        isProcessingRef.current = false
        if (!disposedRef.current && voiceUnlockedRef.current) {
          setStatus('listening')
          startRecordingCycle()
        }
      }
    },
    [patchEntry, startRecordingCycle],
  )

  const finishUtterance = useCallback(() => {
    const recorder = mediaRecorderRef.current
    if (!recorder || recorder.state !== 'recording' || isProcessingRef.current) return
    recorder.stop()
  }, [])

  const monitorVoiceActivity = useCallback(() => {
    const analyser = analyserRef.current
    if (!analyser || isProcessingRef.current) return

    const frequencyData = new Uint8Array(analyser.frequencyBinCount)
    const level = measureVoiceLevel(analyser, frequencyData)
    const now = Date.now()

    if (level >= SPEECH_THRESHOLD) {
      speechDetectedRef.current = true
      if (!speechStartedAtRef.current) {
        speechStartedAtRef.current = now
      }
      silenceStartedAtRef.current = null
      return
    }

    if (!speechDetectedRef.current || !speechStartedAtRef.current) return

    if (!silenceStartedAtRef.current) {
      silenceStartedAtRef.current = now
      return
    }

    const spokeLongEnough = now - speechStartedAtRef.current >= MIN_SPEECH_MS
    const silentLongEnough = now - silenceStartedAtRef.current >= SILENCE_MS
    if (spokeLongEnough && silentLongEnough) {
      finishUtterance()
    }
  }, [finishUtterance])

  const stopVoicePipeline = useCallback(() => {
    if (monitorTimerRef.current) {
      window.clearInterval(monitorTimerRef.current)
      monitorTimerRef.current = null
    }
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop()
    }
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop())
    mediaStreamRef.current = null
    mediaRecorderRef.current = null
    analyserRef.current = null
    setMediaStream(null)
  }, [])

  const unlockVoice = useCallback(async () => {
    setUnlockError('')
    setStatus('unlocking')

    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus('unsupported')
      setUnlockError('Voice capture is not supported in this browser.')
      return
    }

    const mimeType = getRecorderMimeType()
    if (!mimeType) {
      setStatus('unsupported')
      setUnlockError('Audio recording format is not supported in this browser.')
      return
    }

    try {
      stopVoicePipeline()

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
        video: false,
      })

      if (disposedRef.current) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }

      const audioContext = new AudioContext()
      await audioContext.resume()

      const source = audioContext.createMediaStreamSource(stream)
      const analyser = audioContext.createAnalyser()
      analyser.fftSize = 512
      analyser.smoothingTimeConstant = 0.82
      source.connect(analyser)

      const recorder = new MediaRecorder(stream, { mimeType })
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data)
        }
      }
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeType })
        chunksRef.current = []
        speechDetectedRef.current = false
        speechStartedAtRef.current = null
        silenceStartedAtRef.current = null
        void processRecording(blob)
      }

      mediaStreamRef.current = stream
      mediaRecorderRef.current = recorder
      audioContextRef.current = audioContext
      analyserRef.current = analyser
      voiceUnlockedRef.current = true

      setMediaStream(stream)
      setStatus('listening')
      startRecordingCycle()
      monitorTimerRef.current = window.setInterval(monitorVoiceActivity, 80)
    } catch (error) {
      voiceUnlockedRef.current = false
      setStatus('denied')
      setUnlockError(getMediaErrorMessage(error))
    }
  }, [monitorVoiceActivity, processRecording, startRecordingCycle, stopVoicePipeline])

  useEffect(() => {
    disposedRef.current = false

    async function checkBackend() {
      try {
        await checkBackendHealth()
        if (!disposedRef.current) {
          setStatus('awaiting-click')
        }
      } catch {
        if (!disposedRef.current) {
          setStatus('offline')
          setEntries([
            createEntry(
              'error',
              'Backend offline. Start it: cd Backend && source .venv/bin/activate && uvicorn main:app --reload',
            ),
          ])
        }
      }
    }

    void checkBackend()

    return () => {
      disposedRef.current = true
      voiceUnlockedRef.current = false
      stopVoicePipeline()
      if (audioContextRef.current?.state !== 'closed') {
        void audioContextRef.current?.close()
      }
      audioContextRef.current = null
    }
  }, [stopVoicePipeline])

  const needsUnlock = ['awaiting-click', 'denied', 'unlocking'].includes(status)

  return {
    entries,
    status,
    mediaStream,
    needsUnlock,
    unlockVoice,
    unlockError,
  }
}
