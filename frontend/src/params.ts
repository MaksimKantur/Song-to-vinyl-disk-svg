// Mirrors backend/render.py Params.

export type Mode = 'polar' | 'spiral'
export type Encoding = 'gray' | 'width' | 'threshold' | 'dots' | 'hatch' | 'wiggle'

export interface Params {
  mode: Mode
  encoding: Encoding
  start: number
  end: number | null
  rings: number
  segments: number
  gap_deg: number
  bass_center: boolean
  turns: number
  cell_mm: number
  fmin: number
  fmax: number
  range_db: number
  gamma: number
  tilt_db_oct: number
  invert: boolean
  fill: number
  threshold: number
  levels: number
  lines: number
  pen_mm: number
  paper: 'A3' | 'A2'
  landscape: boolean
  margin_mm: number
  hole_mm: number
  outline: boolean
  mirror: boolean
  title: string
  title_size_mm: number
}

export const DEFAULTS: Params = {
  mode: 'polar',
  encoding: 'threshold',
  start: 0,
  end: null,
  rings: 96,
  segments: 480,
  gap_deg: 4,
  bass_center: true,
  turns: 40,
  cell_mm: 1.5,
  fmin: 40,
  fmax: 12000,
  range_db: 45,
  gamma: 1,
  tilt_db_oct: 3,
  invert: false,
  fill: 0.85,
  threshold: 0.5,
  levels: 12,
  lines: 4,
  pen_mm: 0.3,
  paper: 'A2',
  landscape: false,
  margin_mm: 25,
  hole_mm: 8,
  outline: true,
  mirror: false,
  title: '',
  title_size_mm: 6,
}

export const MODES: { value: Mode; label: string; hint: string }[] = [
  { value: 'polar', label: 'Полярная спектрограмма', hint: 'Угол — время, радиус — частота. Как на фото.' },
  { value: 'spiral', label: 'Спираль (винил)', hint: 'Одна дорожка от края к центру, тон — общая громкость.' },
]

export const ENCODINGS: { value: Encoding; label: string; hint: string; lines?: boolean }[] = [
  {
    value: 'threshold',
    label: 'Порог (дуги-штрихи)',
    hint: 'Чисто чёрно-белые штрихи там, где громче порога — ближе всего к фото. Лазер, фотополимер, трафарет.',
  },
  {
    value: 'width',
    label: 'Толщина дорожки',
    hint: 'Ширина чёрной дорожки ∝ громкости. Лазерная гравировка заливкой, фотополимер; в спирали выглядит как канавка винила.',
  },
  {
    value: 'gray',
    label: 'Серая заливка',
    hint: 'Каждый уровень — отдельный оттенок серого. Печать плёнки для фотополимера/офорта; в LightBurn каждый цвет — свой слой со своей мощностью.',
  },
  {
    value: 'dots',
    label: 'Полутоновые точки',
    hint: 'Растр кружками разного размера. Фотополимер, шелкография, трафарет.',
  },
  {
    value: 'hatch',
    label: 'Штриховка линиями',
    hint: 'Только линии без заливок, тон = число параллельных линий. Пен-плоттер, лазер в режиме Line, сухая игла.',
    lines: true,
  },
  {
    value: 'wiggle',
    label: 'Зигзаг-канавка',
    hint: 'Одна непрерывная линия на дорожку, амплитуда = громкость. Пен-плоттер, особенно в режиме спирали.',
    lines: true,
  },
]
