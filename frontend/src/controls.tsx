import type { ReactNode } from 'react'

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="section">
      <legend>{title}</legend>
      {children}
    </fieldset>
  )
}

interface SliderProps {
  label: string
  value: number
  min: number
  max: number
  step?: number
  unit?: string
  onChange: (v: number) => void
}

export function Slider({ label, value, min, max, step = 1, unit, onChange }: SliderProps) {
  return (
    <label className="control">
      <span className="control-label">
        {label}
        <input
          className="number"
          type="number"
          value={value}
          min={min}
          max={max}
          step={step}
          onChange={(e) => {
            const v = e.target.valueAsNumber
            if (!Number.isNaN(v)) onChange(Math.min(max, Math.max(min, v)))
          }}
        />
        {unit && <span className="unit">{unit}</span>}
      </span>
      <input
        type="range"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(e.target.valueAsNumber)}
      />
    </label>
  )
}

interface SelectProps<T extends string> {
  label: string
  value: T
  options: { value: T; label: string }[]
  onChange: (v: T) => void
}

export function Select<T extends string>({ label, value, options, onChange }: SelectProps<T>) {
  return (
    <label className="control">
      <span className="control-label">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value as T)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  )
}

export function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={value} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  )
}

export function Text({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="control">
      <span className="control-label">{label}</span>
      <input type="text" value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  )
}
