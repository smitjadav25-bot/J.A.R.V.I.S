import { useCallback, useEffect, useRef, useState } from 'react'
import './StructuredContent.css'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

function fetchImages(query) {
  const q = encodeURIComponent(query)
  return fetch(`${API_BASE}/api/search-images?q=${q}&count=4`)
    .then((r) => r.json())
    .then((d) => d.images ?? [])
    .catch(() => [])
}

function parseStructured(text) {
  try {
    const obj = JSON.parse(text)
    if (obj && typeof obj === 'object' && (obj.type === 'biography' || obj.type === 'research')) {
      return obj
    }
  } catch {}
  return null
}

function BiographyCard({ data }) {
  const [images, setImages] = useState([])
  const fetchedRef = useRef(false)

  useEffect(() => {
    if (fetchedRef.current) return
    fetchedRef.current = true
    const queries = data.image_searches?.length
      ? data.image_searches
      : [data.image_query || data.name]
    Promise.all(queries.map(fetchImages)).then((results) => {
      setImages(results.flat().slice(0, 6))
    })
  }, [data])

  return (
    <div className="sc-card sc-card--bio">
      <h3 className="sc-name">{data.name}</h3>
      {data.nationality && <span className="sc-meta">{data.nationality}</span>}
      <div className="sc-dates">
        {data.born && <span>Born: {data.born}</span>}
        {data.died && <span>Died: {data.died}</span>}
      </div>

      <p className="sc-summary">{data.summary}</p>

      {data.known_for?.length > 0 && (
        <div className="sc-section">
          <strong>Known for</strong>
          <ul className="sc-list">
            {data.known_for.map((item, i) => <li key={i}>{item}</li>)}
          </ul>
        </div>
      )}

      {images.length > 0 && (
        <div className="sc-images">
          {images.map((img, i) => (
            <img key={i} src={img.url} alt={img.title || data.name} className="sc-img" loading="lazy" />
          ))}
        </div>
      )}

      {data.notable_works?.length > 0 && (
        <div className="sc-section">
          <strong>Notable works</strong>
          <ul className="sc-list">
            {data.notable_works.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </div>
      )}

      {data.quotes?.length > 0 && (
        <div className="sc-quotes">
          {data.quotes.map((q, i) => (
            <blockquote key={i} className="sc-quote">&ldquo;{q}&rdquo;</blockquote>
          ))}
        </div>
      )}

      {data.video_searches?.length > 0 && (
        <div className="sc-videos">
          {data.video_searches.map((v, i) => (
            <div key={i} className="sc-video-embed">
              <iframe
                src={`https://www.youtube.com/embed?listType=search&list=${encodeURIComponent(v)}`}
                title={v}
                allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
                loading="lazy"
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ResearchCard({ data }) {
  const [sections, setSections] = useState([])
  const fetchedRef = useRef(false)

  const sectionQueries = [
    data.banner_query,
    ...(data.sections?.map((s) => s.image_query).filter(Boolean) ?? []),
  ].filter(Boolean)

  useEffect(() => {
    if (fetchedRef.current) return
    fetchedRef.current = true
    if (sectionQueries.length === 0) return
    Promise.all(sectionQueries.map(fetchImages)).then((results) => {
      const map = {}
      let idx = 0
      if (data.banner_query) {
        map.banner = results[idx]?.[0]?.url ?? null
        idx++
      }
      const sectionImages = {}
      for (const s of data.sections ?? []) {
        if (s.image_query) {
          sectionImages[s.title] = results[idx]?.[0]?.url ?? null
          idx++
        }
      }
      setSections(
        (data.sections ?? []).map((s) => ({
          ...s,
          imageUrl: sectionImages[s.title] || null,
        })),
      )
    })
  }, [data])

  return (
    <div className="sc-card sc-card--research">
      <h3 className="sc-topic">{data.topic}</h3>
      <p className="sc-summary">{data.summary}</p>

      {data.banner_query && <div className="sc-banner-placeholder" />}

      {sections.length > 0 && (
        <div className="sc-sections">
          {sections.map((sec, i) => (
            <div key={i} className="sc-section-block">
              {sec.imageUrl && (
                <img src={sec.imageUrl} alt={sec.title} className="sc-section-img" loading="lazy" />
              )}
              <h4 className="sc-section-title">{sec.title}</h4>
              <p className="sc-section-text">{sec.content}</p>
            </div>
          ))}
        </div>
      )}

      {data.key_facts?.length > 0 && (
        <div className="sc-section">
          <strong>Key facts</strong>
          <ul className="sc-list">
            {data.key_facts.map((f, i) => <li key={i}>{f}</li>)}
          </ul>
        </div>
      )}

      {data.related_topics?.length > 0 && (
        <div className="sc-section">
          <strong>Related topics</strong>
          <div className="sc-tags">
            {data.related_topics.map((t, i) => (
              <span key={i} className="sc-tag">{t}</span>
            ))}
          </div>
        </div>
      )}

      {data.video_searches?.length > 0 && (
        <div className="sc-videos">
          {data.video_searches.map((v, i) => (
            <div key={i} className="sc-video-embed">
              <iframe
                src={`https://www.youtube.com/embed?listType=search&list=${encodeURIComponent(v)}`}
                title={v}
                allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
                loading="lazy"
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function isStructuredText(text) {
  return !!parseStructured(text)
}

export default function StructuredContent({ text }) {
  if (!text) return null
  const data = parseStructured(text)
  if (!data) return null
  return data.type === 'biography' ? <BiographyCard data={data} /> : <ResearchCard data={data} />
}
