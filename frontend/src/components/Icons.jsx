import React from 'react'
const paths = {
  dashboard: <><rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/></>,
  prospects: <><circle cx="9" cy="8" r="4"/><path d="M3 21v-2a6 6 0 0 1 12 0v2"/><path d="M17 8h4M19 6v4"/></>,
  actions: <><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></>,
  pipeline: <><path d="M3 5h18M6 12h12M9 19h6"/><circle cx="6" cy="5" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="15" cy="19" r="2"/></>,
  forecast: <><path d="M3 3v18h18"/><path d="M7 15l4-4 3 2 5-7"/><path d="M16 6h3v3"/></>,
  leadership: <><path d="M4 19V9M10 19V5M16 19v-7M22 19V3"/><path d="M2 21h22"/></>,
  search: <><circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/></>,
  bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/></>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.8 1.8 0 0 0 .4 2l.1.1-2.8 2.8-.1-.1a1.8 1.8 0 0 0-2-.4 1.8 1.8 0 0 0-1 1.6V21h-4v-.1a1.8 1.8 0 0 0-1-1.6 1.8 1.8 0 0 0-2 .4l-.1.1-2.8-2.8.1-.1a1.8 1.8 0 0 0 .4-2A1.8 1.8 0 0 0 3 14H3v-4h.1a1.8 1.8 0 0 0 1.6-1 1.8 1.8 0 0 0-.4-2l-.1-.1L7 4.1l.1.1a1.8 1.8 0 0 0 2 .4A1.8 1.8 0 0 0 10 3V3h4v.1a1.8 1.8 0 0 0 1 1.6 1.8 1.8 0 0 0 2-.4l.1-.1L20 7l-.1.1a1.8 1.8 0 0 0-.4 2A1.8 1.8 0 0 0 21 10h.1v4H21a1.8 1.8 0 0 0-1.6 1z"/></>,
  plus: <><path d="M12 5v14M5 12h14"/></>,
  chevron: <path d="M9 18l6-6-6-6"/>,
  close: <><path d="M6 6l12 12M18 6L6 18"/></>,
  company: <><path d="M3 21h18M5 21V7l7-4v18M19 21V11l-7-3"/><path d="M8 9h1M8 13h1M8 17h1M15 13h1M15 17h1"/></>,
  meeting: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/></>,
  note: <><path d="M4 3h13l3 3v15H4z"/><path d="M17 3v4h4M8 11h8M8 15h8"/></>,
  target: <><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/></>,
  arrow: <><path d="M5 12h14M13 6l6 6-6 6"/></>,
  logout: <><path d="M10 17l5-5-5-5M15 12H3"/><path d="M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5"/></>,
  refresh: <><path d="M20 6v5h-5"/><path d="M4 18v-5h5"/><path d="M18.5 9A7 7 0 0 0 6 6.5L4 11M5.5 15A7 7 0 0 0 18 17.5L20 13"/></>,
  filter: <path d="M4 5h16l-6 7v6l-4 2v-8z"/>,
  eye: <><path d="M2 12s4-6 10-6 10 6 10 6-4 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="2.5"/></>,
  check: <path d="M5 12l4 4L19 6"/>,
  mail: <><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/></>,
  lock: <><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></>,
  edit: <><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.1 2.1 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></>,
  trash: <><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></>
}
export function Icon({ name, size = 20, className = '' }) {
  return <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.note}</svg>
}
