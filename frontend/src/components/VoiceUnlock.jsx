import './VoiceUnlock.css'

export default function VoiceUnlock({ onUnlock, status, errorMessage }) {
  const isDenied = status === 'denied'
  const isUnlocking = status === 'unlocking'

  return (
    <div className="voice-unlock">
      <div className="voice-unlock__card">
        <h2 className="voice-unlock__title">Enable J.A.R.V.I.S. Voice</h2>
        <p className="voice-unlock__text">
          Your browser requires a click before microphone and speech playback can start.
          Click below, then allow microphone access when prompted.
        </p>
        {errorMessage && <p className="voice-unlock__error">{errorMessage}</p>}
        <button
          type="button"
          className="voice-unlock__button"
          onClick={onUnlock}
          disabled={isUnlocking}
        >
          {isUnlocking ? 'Enabling…' : isDenied ? 'Try again' : 'Enable voice'}
        </button>
      </div>
    </div>
  )
}
