import { useEffect, useMemo, useState } from 'react'
import { renderSvg, uploadTrack, type TrackInfo } from './api'
import { Section, Select, Slider, Text, Toggle } from './controls'
import { DEFAULTS, ENCODINGS, MODES, type Params } from './params'

const RENDER_DEBOUNCE_MS = 350

function formatTime(sec: number) {
  const m = Math.floor(sec / 60)
  const s = (sec % 60).toFixed(1).padStart(4, '0')
  return `${m}:${s}`
}

export default function App() {
  const [track, setTrack] = useState<TrackInfo | null>(null)
  const [params, setParams] = useState<Params>(DEFAULTS)
  const [svg, setSvg] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [rendering, setRendering] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const set = <K extends keyof Params>(key: K) => (value: Params[K]) => setParams((p) => ({ ...p, [key]: value }))

  async function onFile(file: File) {
    setUploading(true)
    setError(null)
    try {
      const info = await uploadTrack(file)
      setTrack(info)
      setParams((p) => ({ ...p, start: 0, end: null, title: info.title }))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setUploading(false)
    }
  }

  useEffect(() => {
    if (!track) return
    const ctrl = new AbortController()
    const timer = setTimeout(async () => {
      setRendering(true)
      try {
        setSvg(await renderSvg(track.id, params, ctrl.signal))
        setError(null)
      } catch (e) {
        if (!ctrl.signal.aborted) setError((e as Error).message)
      } finally {
        if (!ctrl.signal.aborted) setRendering(false)
      }
    }, RENDER_DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      ctrl.abort()
    }
  }, [track, params])

  const previewUrl = useMemo(() => (svg ? URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' })) : null), [svg])
  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
  }, [previewUrl])

  function download() {
    if (!previewUrl || !track) return
    const stem = track.name.replace(/\.[^.]+$/, '')
    const a = document.createElement('a')
    a.href = previewUrl
    a.download = `${stem}_${params.mode}_${params.encoding}.svg`
    a.click()
  }

  const encoding = ENCODINGS.find((e) => e.value === params.encoding)!
  const mode = MODES.find((m) => m.value === params.mode)!
  const duration = track?.duration ?? 0
  const polar = params.mode === 'polar'

  return (
    <div className="app">
      <aside className="panel">
        <h1>Song → SVG</h1>

        <Section title="Трек">
          <label className={`dropzone ${uploading ? 'busy' : ''}`}>
            <input
              type="file"
              accept="audio/*,.flac,.ogg,.opus,.m4a,.wav,.mp3"
              onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
            />
            {uploading ? 'Анализирую…' : track ? `${track.name} (${formatTime(track.duration)})` : 'Выбрать аудиофайл'}
          </label>
          {track && (
            <>
              <Slider label={`Начало ${formatTime(params.start)}`} value={params.start} min={0} max={duration} step={0.1} unit="с" onChange={set('start')} />
              <Slider
                label={`Конец ${formatTime(params.end ?? duration)}`}
                value={params.end ?? duration}
                min={0}
                max={duration}
                step={0.1}
                unit="с"
                onChange={(v) => set('end')(v >= duration ? null : v)}
              />
            </>
          )}
        </Section>

        <Section title="Режим">
          <Select label="Геометрия" value={params.mode} options={MODES} onChange={set('mode')} />
          <p className="hint">{mode.hint}</p>
          {polar ? (
            <>
              <Slider label="Колец (частотных полос)" value={params.rings} min={4} max={400} onChange={set('rings')} />
              <Slider label="Сегментов по времени" value={params.segments} min={16} max={2000} step={8} onChange={set('segments')} />
              <Slider label="Зазор начало/конец" value={params.gap_deg} min={0} max={90} step={0.5} unit="°" onChange={set('gap_deg')} />
              <Toggle label="Басы в центре" value={params.bass_center} onChange={set('bass_center')} />
            </>
          ) : (
            <>
              <Slider label="Витков" value={params.turns} min={1} max={300} onChange={set('turns')} />
              <Slider label="Длина ячейки" value={params.cell_mm} min={0.2} max={20} step={0.1} unit="мм" onChange={set('cell_mm')} />
            </>
          )}
        </Section>

        <Section title="Кодировка тона">
          <Select label="Способ" value={params.encoding} options={ENCODINGS} onChange={set('encoding')} />
          <p className="hint">{encoding.hint}</p>
          <Slider label="Заполнение дорожки" value={params.fill} min={0.05} max={1} step={0.01} onChange={set('fill')} />
          {params.encoding === 'threshold' && (
            <Slider label="Порог" value={params.threshold} min={0} max={1} step={0.01} onChange={set('threshold')} />
          )}
          {params.encoding === 'gray' && (
            <Slider label="Уровней серого" value={params.levels} min={2} max={64} onChange={set('levels')} />
          )}
          {params.encoding === 'hatch' && (
            <Slider label="Линий на дорожку" value={params.lines} min={1} max={12} onChange={set('lines')} />
          )}
          {(encoding.lines || params.outline) && (
            <Slider label="Толщина пера / линии" value={params.pen_mm} min={0.02} max={3} step={0.01} unit="мм" onChange={set('pen_mm')} />
          )}
        </Section>

        <Section title="Спектр → тон">
          <Slider label="Мин. частота" value={params.fmin} min={10} max={4000} step={10} unit="Гц" onChange={set('fmin')} />
          <Slider label="Макс. частота" value={params.fmax} min={200} max={16000} step={100} unit="Гц" onChange={set('fmax')} />
          <Slider label="Динамический диапазон" value={params.range_db} min={6} max={120} unit="дБ" onChange={set('range_db')} />
          <Slider label="Гамма (контраст)" value={params.gamma} min={0.2} max={5} step={0.05} onChange={set('gamma')} />
          {polar && (
            <Slider label="Подъём верхов" value={params.tilt_db_oct} min={-6} max={12} step={0.5} unit="дБ/окт" onChange={set('tilt_db_oct')} />
          )}
          <Toggle label="Инверсия (тихо = чёрное)" value={params.invert} onChange={set('invert')} />
        </Section>

        <Section title="Лист">
          <Select
            label="Формат"
            value={params.paper}
            options={[
              { value: 'A2', label: 'A2 (420 × 594 мм)' },
              { value: 'A3', label: 'A3 (297 × 420 мм)' },
            ]}
            onChange={set('paper')}
          />
          <Toggle label="Альбомная ориентация" value={params.landscape} onChange={set('landscape')} />
          <Slider label="Поля" value={params.margin_mm} min={0} max={150} unit="мм" onChange={set('margin_mm')} />
          <Slider label="Центральное отверстие (радиус)" value={params.hole_mm} min={0} max={100} step={0.5} unit="мм" onChange={set('hole_mm')} />
          <Toggle label="Контур диска" value={params.outline} onChange={set('outline')} />
          <Toggle label="Зеркалить для печати" value={params.mirror} onChange={set('mirror')} />
          <Text label="Подпись" value={params.title} onChange={set('title')} />
          {params.title.trim() && (
            <Slider label="Размер подписи" value={params.title_size_mm} min={1} max={40} step={0.5} unit="мм" onChange={set('title_size_mm')} />
          )}
        </Section>

        <button className="reset" onClick={() => setParams((p) => ({ ...DEFAULTS, start: p.start, end: p.end, title: p.title }))}>
          Сбросить настройки
        </button>
      </aside>

      <main className="stage">
        <div className="toolbar">
          <span className="status">
            {error ? <span className="error">{error}</span> : rendering ? 'Рисую…' : svg ? `SVG: ${(svg.length / 1e6).toFixed(2)} МБ` : ''}
          </span>
          <button className="primary" disabled={!svg} onClick={download}>
            Скачать SVG
          </button>
        </div>
        <div className={`preview ${rendering ? 'stale' : ''}`}>
          {previewUrl ? <img src={previewUrl} alt="Превью" /> : <p className="empty">Загрузи аудиофайл слева</p>}
        </div>
      </main>
    </div>
  )
}
