/*
 * The persistent frame: a quiet left rail, and everything else given to the
 * investigation. The rail never grows louder than the workspace it sits beside.
 */

import { NavLink } from 'react-router-dom'
import Icon from '../common/Icon.jsx'
import CommandPalette from './CommandPalette.jsx'
import { useInvestigation } from '../../state/InvestigationContext.jsx'
import { CASE_STATUS_LABEL } from '../../lib/domain.js'
import { caseShortName } from '../../lib/format.js'
import './shell.css'

const NAV = [
  { to: '/', label: 'Overview', icon: 'overview', end: true },
  { to: '/network', label: 'Network', icon: 'network' },
  { to: '/entities', label: 'Entities', icon: 'entities' },
  { to: '/evidence', label: 'Evidence', icon: 'evidence' },
  { to: '/timeline', label: 'Timeline', icon: 'timeline' },
  { to: '/analytics', label: 'Analytics', icon: 'analytics' },
  { to: '/leads', label: 'Leads', icon: 'leads' },
]

function TraceMark() {
  /* Three points and the line that joins them: the product in one glyph. */
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" className="mark">
      <path
        d="M3.4 13.6C6 13.2 6.6 9 9 8.2c2-.7 3.3 1 5.4.4"
        fill="none"
        stroke="var(--trace-line)"
        strokeWidth="1.3"
        strokeLinecap="round"
      />
      <circle cx="3.4" cy="13.6" r="2" fill="var(--surface)" stroke="var(--ink)" strokeWidth="1.3" />
      <circle cx="9" cy="8.2" r="2" fill="var(--trace)" />
      <circle cx="14.6" cy="4.4" r="2" fill="var(--surface)" stroke="var(--ink)" strokeWidth="1.3" />
    </svg>
  )
}

function CaseSwitcher() {
  const { cases, caseTriage, caseId, setCaseId, core } = useInvestigation()
  const list = cases.data?.investigations ?? []
  const summary = core.data?.summary
  const triage = caseTriage[caseId]

  return (
    <div className="caseswitch">
      <label className="eyebrow" htmlFor="case-select">
        Case
      </label>
      <select
        id="case-select"
        className="select caseswitch__select"
        value={caseId ?? ''}
        onChange={(event) => setCaseId(event.target.value)}
        disabled={!list.length}
      >
        {!list.length ? <option value="">No investigations</option> : null}
        {list.map((item) => (
          <option key={item.case_id} value={item.case_id}>
            {caseShortName(item.case_id)}
          </option>
        ))}
      </select>
      {summary ? (
        <div className="caseswitch__meta">
          <span className="mono">{summary.case_id}</span>
          <span className={`pill pill--square pill--${summary.status === 'closed' ? 'low' : 'medium'}`}>
            {CASE_STATUS_LABEL[summary.status] ?? summary.status}
          </span>
        </div>
      ) : null}
      {triage ? (
        <div className="caseswitch__triage" title="Leads raised for this investigation by priority">
          {(['high', 'medium', 'low']).map((level) =>
            triage[level] ? (
              <span key={level} className={`pill pill--square pill--${level}`}>
                {triage[level]} {level}
              </span>
            ) : null,
          )}
          {triage.total === 0 ? <span className="caseswitch__none">No leads raised</span> : null}
        </div>
      ) : null}
    </div>
  )
}

export function AppShell({ children }) {
  const { core, index } = useInvestigation()
  const counts = index.counts

  return (
    <div className="shell">
      <nav className="rail" aria-label="Investigation sections">
        <div className="rail__brand">
          <TraceMark />
          <span className="rail__wordmark">
            Silent<span>Trace</span>
          </span>
        </div>

        <CaseSwitcher />

        <ul className="rail__nav">
          {NAV.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.end}
                className={({ isActive }) => `railitem${isActive ? ' is-active' : ''}`}
              >
                <Icon name={item.icon} size={14} />
                <span>{item.label}</span>
                {item.to === '/entities' && counts.entities ? (
                  <span className="railitem__count num">{counts.entities}</span>
                ) : null}
                {item.to === '/evidence' && counts.evidence ? (
                  <span className="railitem__count num">{counts.evidence}</span>
                ) : null}
              </NavLink>
            </li>
          ))}
        </ul>

        <div className="rail__foot">
          <button
            type="button"
            className="railsearch"
            onClick={() =>
              window.dispatchEvent(
                new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true }),
              )
            }
          >
            <Icon name="search" size={12} />
            <span>Search</span>
            <kbd>Ctrl K</kbd>
          </button>
          <p className="rail__note">
            Synthetic data only. Analytical signals are decision support, never proof.
          </p>
          {core.data?.summary ? (
            <p className="rail__graph mono">{core.data.summary.graph_id ?? 'no graph'}</p>
          ) : null}
        </div>
      </nav>

      <div className="workspace">{children}</div>

      <CommandPalette />
    </div>
  )
}

/**
 * The strip above every page: what this case is, and how big it is.
 * `actions` is where a page puts its own controls, so the header shape stays
 * identical across pages while the controls stay page-specific.
 */
export function PageHeader({ title, description, actions, meta }) {
  return (
    <header className="pagehead">
      <div className="pagehead__main">
        <div className="pagehead__title">
          <h1>{title}</h1>
          {meta}
        </div>
        {description ? <p className="pagehead__desc">{description}</p> : null}
      </div>
      {actions ? <div className="pagehead__actions">{actions}</div> : null}
    </header>
  )
}
