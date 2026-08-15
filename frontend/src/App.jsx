import { useEffect } from 'react'
import GeometricAuraBlob from './components/GeometricAuraBlob'
import Terminal from './components/Terminal'
import { useJarvis } from './hooks/useJarvis'
import './App.css'

function App() {
  const { entries, status, mediaStream, needsUnlock, unlockVoice, unlockError } = useJarvis()

  useEffect(() => {
    if (needsUnlock) {
      unlockVoice()
    }
  }, [needsUnlock, unlockVoice])

  return (
    <div className="app-shell">
      <GeometricAuraBlob mediaStream={mediaStream} />
      <Terminal entries={entries} status={status} />
    </div>
  )
}

export default App
