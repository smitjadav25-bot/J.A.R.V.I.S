import { useEffect, useRef, useState } from 'react'
import './GeometricAuraBlob.css'

const VERTICES = [
  [0, 1.2, 0],
  [0, -1.2, 0],
  [1.05, 0.38, 0.68],
  [1.05, 0.38, -0.68],
  [-1.05, 0.38, 0.68],
  [-1.05, 0.38, -0.68],
  [0.68, -0.38, 1.05],
  [0.68, -0.38, -1.05],
  [-0.68, -0.38, 1.05],
  [-0.68, -0.38, -1.05],
  [0, 0.75, 1.05],
  [0, 0.75, -1.05],
]

const EDGES = [
  [0, 2], [0, 3], [0, 4], [0, 5], [0, 10], [0, 11],
  [1, 6], [1, 7], [1, 8], [1, 9],
  [2, 3], [2, 6], [2, 10], [3, 7], [3, 11], [4, 8], [4, 10],
  [5, 9], [5, 11], [6, 8], [7, 9], [10, 8], [11, 9],
]

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value))
}

function rotateY([x, y, z], angle) {
  const c = Math.cos(angle)
  const s = Math.sin(angle)
  return [x * c + z * s, y, -x * s + z * c]
}

function rotateX([x, y, z], angle) {
  const c = Math.cos(angle)
  const s = Math.sin(angle)
  return [x, y * c - z * s, y * s + z * c]
}

function project([x, y, z], width, height, scale) {
  const fov = 2.8
  const depth = fov + z
  const px = width / 2 + (x * scale * fov) / depth
  const py = height / 2 - (y * scale * fov) / depth
  return [px, py, depth]
}

function createStars(count) {
  return Array.from({ length: count }, () => ({
    x: Math.random() * 2 - 1,
    y: Math.random() * 2 - 1,
    z: Math.random(),
    size: 0.4 + Math.random() * 1.2,
    twinkle: Math.random() * Math.PI * 2,
  }))
}

export default function GeometricAuraBlob({ mediaStream: sharedStream = null }) {
  const canvasRef = useRef(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return undefined

    const ctx = canvas.getContext('2d')
    if (!ctx) return undefined

    let width = 0
    let height = 0
    let animationId = 0
    let disposed = false
    let time = 0

    const stars = createStars(120)
    const ringDots = Array.from({ length: 48 }, (_, i) => {
      const t = (i / 48) * Math.PI * 2
      return { t, hue: (i / 48) * 360 }
    })

    const audioLevel = { current: 0, target: 0 }
    let audioContext = null
    let analyser = null
    let frequencyData = null
    let mediaStream = null
    let ownsStream = false

    const hideLoadingTimer = window.setTimeout(() => setLoading(false), 300)

    async function initMicrophone() {
      try {
        if (sharedStream) {
          mediaStream = sharedStream
          ownsStream = false
        } else {
          mediaStream = await navigator.mediaDevices.getUserMedia({
            audio: {
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
            },
            video: false,
          })
          ownsStream = true
        }
        if (disposed) return

        audioContext = new AudioContext()
        const source = audioContext.createMediaStreamSource(mediaStream)
        analyser = audioContext.createAnalyser()
        analyser.fftSize = 512
        analyser.smoothingTimeConstant = 0.82
        source.connect(analyser)
        frequencyData = new Uint8Array(analyser.frequencyBinCount)
      } catch {
        // Blob keeps ambient animation when mic is unavailable.
      }
    }

    void initMicrophone()

    function resize() {
      const parent = canvas.parentElement
      if (!parent) return
      width = parent.clientWidth
      height = parent.clientHeight
      const dpr = Math.min(window.devicePixelRatio, 2)
      canvas.width = Math.floor(width * dpr)
      canvas.height = Math.floor(height * dpr)
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    function sampleAudioLevel() {
      if (!analyser || !frequencyData) {
        audioLevel.target = 0
        return
      }

      analyser.getByteFrequencyData(frequencyData)
      let sum = 0
      const voiceBandEnd = Math.floor(frequencyData.length * 0.45)
      for (let i = 2; i < voiceBandEnd; i += 1) {
        sum += frequencyData[i]
      }
      const average = sum / (voiceBandEnd - 2)
      audioLevel.target = clamp((average / 110) ** 0.65, 0, 1)
    }

    function smoothAudioLevel() {
      const rate = audioLevel.target > audioLevel.current ? 0.28 : 0.1
      audioLevel.current += (audioLevel.target - audioLevel.current) * rate
    }

    function drawFrame() {
      if (disposed) return
      animationId = requestAnimationFrame(drawFrame)
      time += 0.012
      sampleAudioLevel()
      smoothAudioLevel()

      const voice = audioLevel.current
      const breathe = 0.04 * Math.sin(time * 2.1)
      const scale = 90 * (1 + voice * 0.62 + breathe)

      const bg = ctx.createRadialGradient(
        width * 0.2,
        height * 0.3,
        0,
        width * 0.5,
        height * 0.5,
        Math.max(width, height) * 0.8,
      )
      bg.addColorStop(0, '#0a1428')
      bg.addColorStop(1, '#050a14')
      ctx.fillStyle = bg
      ctx.fillRect(0, 0, width, height)

      for (const star of stars) {
        const sx = (star.x * 0.5 + 0.5) * width
        const sy = (star.y * 0.5 + 0.5) * height
        const alpha = 0.25 + 0.35 * (0.5 + 0.5 * Math.sin(time * 2 + star.twinkle))
        ctx.fillStyle = `rgba(170, 187, 255, ${alpha})`
        ctx.beginPath()
        ctx.arc(sx, sy, star.size, 0, Math.PI * 2)
        ctx.fill()
      }

      const cx = width / 2
      const cy = height / 2
      const rotY = time * 0.25
      const rotX = 0.2 * Math.sin(time * 0.37)

      const transformed = VERTICES.map((vertex) => {
        let point = rotateY(vertex, rotY)
        point = rotateX(point, rotX)
        return project(point, width, height, scale)
      })

      const glow = 0.35 + voice * 0.55
      ctx.globalCompositeOperation = 'lighter'

      for (const dot of ringDots) {
        const ringX = Math.cos(dot.t + time * 0.35) * (1.55 + voice * 0.08)
        const ringY = Math.sin(dot.t * 3 + time * 0.28) * 0.35
        const [px, py] = project(
          rotateY(rotateX([ringX, ringY, 0], rotX), rotY),
          width,
          height,
          scale,
        )
        const hue = (dot.hue + time * 40) % 360
        ctx.fillStyle = `hsla(${hue}, 80%, 70%, ${0.35 + voice * 0.3})`
        ctx.beginPath()
        ctx.arc(px, py, 2 + voice * 1.2, 0, Math.PI * 2)
        ctx.fill()
      }

      ctx.globalCompositeOperation = 'source-over'

      for (const [a, b] of EDGES) {
        const [x1, y1, z1] = transformed[a]
        const [x2, y2, z2] = transformed[b]
        const depth = (z1 + z2) / 2
        const alpha = clamp(0.2 + (2.5 - depth) * 0.25 + voice * 0.35, 0.15, 0.95)
        ctx.strokeStyle = `rgba(102, 153, 255, ${alpha})`
        ctx.lineWidth = 1 + voice * 0.8
        ctx.beginPath()
        ctx.moveTo(x1, y1)
        ctx.lineTo(x2, y2)
        ctx.stroke()
      }

      const faces = transformed.map(([, , z]) => z)
      const avgDepth = faces.reduce((sum, z) => sum + z, 0) / faces.length
      const coreAlpha = clamp(0.35 + (2.2 - avgDepth) * 0.2 + glow * 0.25, 0.3, 0.9)

      ctx.beginPath()
      for (let i = 0; i < transformed.length; i += 1) {
        const [x, y] = transformed[i]
        if (i === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      }
      ctx.closePath()
      const fill = ctx.createRadialGradient(cx, cy, scale * 0.05, cx, cy, scale * 0.35)
      fill.addColorStop(0, `rgba(120, 180, 255, ${coreAlpha})`)
      fill.addColorStop(1, `rgba(40, 80, 160, ${coreAlpha * 0.35})`)
      ctx.fillStyle = fill
      ctx.fill()

      ctx.strokeStyle = `rgba(136, 204, 255, ${0.45 + voice * 0.4})`
      ctx.lineWidth = 1.5
      ctx.beginPath()
      ctx.arc(cx, cy, scale * 0.42, 0, Math.PI * 2)
      ctx.stroke()

      ctx.beginPath()
      ctx.arc(cx, cy, scale * 0.48, time * 0.5, time * 0.5 + Math.PI * 1.35)
      ctx.strokeStyle = `rgba(255, 170, 136, ${0.25 + voice * 0.35})`
      ctx.lineWidth = 1
      ctx.stroke()
    }

    resize()
    const resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(canvas.parentElement ?? canvas)
    drawFrame()

    return () => {
      disposed = true
      window.clearTimeout(hideLoadingTimer)
      cancelAnimationFrame(animationId)
      resizeObserver.disconnect()
      if (ownsStream) {
        mediaStream?.getTracks().forEach((track) => track.stop())
      }
      if (audioContext?.state !== 'closed') {
        void audioContext?.close()
      }
    }
  }, [sharedStream])

  return (
    <div className="geometric-aura-root">
      <canvas ref={canvasRef} className="geometric-aura-canvas" aria-hidden />
      {loading && <div className="geometric-aura-loading">Loading visual engine...</div>}
    </div>
  )
}
