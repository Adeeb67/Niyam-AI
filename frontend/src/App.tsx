import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, ArrowDownToLine, ArrowLeftRight, Bell, BookOpen, Building2, Check, ChevronDown, CircleHelp, Clock3, FilePlus2, FileText, Gauge, Landmark, LoaderCircle, Plus, RefreshCw, Search, ShieldCheck, SlidersHorizontal, Upload, X } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import LandingPage from './LandingPage'

const API = import.meta.env.VITE_API_BASE_URL || ''
type Page = 'Overview' | 'Sources' | 'Document library' | 'Compare' | 'SME profiles' | 'Action center' | 'Reports'
type Doc = { id: number; regulation_id: string; title: string; authority: string; category: string; jurisdiction: string | null; industry: string | null; publication_date: string | null; effective_date: string | null; version_label: string | null; status: string; content_hash: string; previous_version_id: number | null; error: string | null }
type Profile = { id: number; name: string; industry: string; activities: string; state: string; employee_count: number | null; annual_turnover: string | null; registrations: string; jurisdictions?: string[]; facilities?: string[]; operational_facts?: Record<string, string | number | boolean> }
type Analysis = { id: number; old_title: string; new_title: string; created_at: string; profile_id?: number | null; profile_name?: string | null; applicability?: { outcome: string; reason: string }; summary?: { counts?: Record<string, number>; meaningful_changes?: number }; is_comparison?: boolean }
type Finding = { change_id: string; category: string; previous_text: string | null; updated_text: string | null; summary: string; applicability: 'APPLICABLE' | 'NOT_APPLICABLE' | 'NEEDS_VERIFICATION'; applicability_reason: string; applicable_conditions: string[]; matching_business_characteristics: string[]; exemptions: string[]; business_impact: string; required_action: string; priority: string; priority_rationale: string; publication_date: string | null; effective_date: string | null; compliance_deadline: string | null; deadline_status: string; evidence: { document_version_id: string; clause_id: string | null; page_number: number; quoted_text: string; source_role: string; verified: boolean }[]; missing_information: string[]; follow_up_questions: string[]; review_required: boolean; review_status: string }
type Action = { id: number; analysis_id: number; title: string; description: string; priority: string; deadline: string | null; deadline_status?: string; status: string; evidence: string; profile_id?: number; regulation_id?: string; change_id?: string; assigned_role?: string | null }
type DashboardMetrics = { regulatory_records: number; document_versions: number; detected_changes: number; applicable_changes: number; not_applicable_changes: number; verification_needed: number; open_actions: number; upcoming_verified_deadlines: number; failed_ingestion_or_analysis_jobs: number; recent_completed_analyses: number; changes_over_time?: { month: string; count: number }[]; changes_by_category?: { category: string; count: number }[]; changes_by_applicability?: { applicability: string; count: number }[]; actions_by_priority?: { priority: string; count: number }[]; recent_analyses?: { id: number; old_title: string; new_title: string; created_at: string }[] }
type DashboardImpact = { profile: { id: number; name: string }; analysis_id: number | null; created_at: string | null; source_title: string | null; what_changed: string; business_impact: string; required_action: string; deadline: string | null; deadline_status: string; findings: { change_id: string; category: string; summary: string; applicability: string; business_impact: string; required_action: string; effective_date: string | null; compliance_deadline: string | null; deadline_status: string; priority: string; priority_rationale: string; evidence: Finding['evidence'] }[] }
type SyncRun = { id: number; status: string; discovered: number; downloaded: number; skipped: number; updated: number; failed: number; detail: string; started_at: string; finished_at: string | null }
type Sync = { running: boolean; enabled: boolean; interval_minutes: number; next_sync: string | null; latest?: SyncRun | null }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, { credentials: 'include', ...init })
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(data?.detail || `Request failed (${response.status})`)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

const nav: { name: Page; icon: typeof Gauge; group: string }[] = [
  { name: 'Overview', icon: Gauge, group: 'WORKSPACE' }, { name: 'Sources', icon: Activity, group: 'WORKSPACE' },
  { name: 'Document library', icon: BookOpen, group: 'WORKSPACE' }, { name: 'Compare', icon: ArrowLeftRight, group: 'WORKSPACE' },
  { name: 'SME profiles', icon: Building2, group: 'MANAGE' }, { name: 'Action center', icon: Check, group: 'MANAGE' }, { name: 'Reports', icon: FileText, group: 'MANAGE' },
]

export default function App() {
  const [user, setUser] = useState<{id:number;name:string;email:string;role:string}|null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [authError, setAuthError] = useState('')
  const [adminData, setAdminData] = useState<{total:number;users:{id:number;name:string;email:string;role:string;created_at:string}[];limit:number;offset:number}|null>(null)
  const path = window.location.pathname
  const authPage = ['/signup','/signin','/admin/login'].includes(path)
  const isAdmin = path === '/admin'
  useEffect(() => { request<{id:number;name:string;email:string;role:string}>('/api/auth/me').then(setUser).catch(() => {}).finally(() => setAuthLoading(false)) }, [])
  useEffect(() => { if (isAdmin && user?.role === 'admin') request<typeof adminData>('/api/admin/users?limit=50&offset=0').then(setAdminData).catch(error => setAuthError(error.message)) }, [isAdmin,user])
  const [appEntered] = useState(path === '/app')
  const [page, setPage] = useState<Page>('Overview')
  const [search, setSearch] = useState('')
  const [documentStatus, setDocumentStatus] = useState('')
  const [documentOffset, setDocumentOffset] = useState(0)
  const [documentSort, setDocumentSort] = useState('recent')
  const [notice, setNotice] = useState('')
  const [reportId, setReportId] = useState<number | null>(null)
  const [dashboardRange, setDashboardRange] = useState<'all' | '30d'>('all')
  const queryClient = useQueryClient()
  const docsQuery = useQuery({ queryKey: ['documents', search, documentStatus, documentOffset], queryFn: () => request<{ data: Doc[] }>(`/api/regulations?q=${encodeURIComponent(search)}&status=${encodeURIComponent(documentStatus)}&offset=${documentOffset}&limit=25`), refetchInterval: appEntered ? 15000 : false, enabled: appEntered })
  const profilesQuery = useQuery({ queryKey: ['profiles'], queryFn: () => request<Profile[]>('/api/business-profiles'), enabled: appEntered })
  const analysesQuery = useQuery({ queryKey: ['analyses'], queryFn: () => request<Analysis[]>('/api/impact-analysis'), enabled: appEntered })
  const rangeStart = dashboardRange === '30d' ? new Date(Date.now() - 29 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10) : ''
  const rangeEnd = dashboardRange === '30d' ? new Date().toISOString().slice(0, 10) : ''
  const metricsQuery = useQuery({ queryKey: ['dashboard-metrics', dashboardRange], queryFn: () => request<DashboardMetrics>(`/api/dashboard/metrics${dashboardRange === '30d' ? `?start_date=${rangeStart}&end_date=${rangeEnd}` : ''}`), refetchInterval: appEntered ? 15000 : false, enabled: appEntered })
  const actionsQuery = useQuery({ queryKey: ['actions'], queryFn: () => request<Action[]>('/api/actions'), enabled: appEntered })
  const syncQuery = useQuery({ queryKey: ['sync'], queryFn: () => request<Sync>('/api/sources/sync/status'), refetchInterval: appEntered ? 4000 : false, enabled: appEntered })
  const docs = docsQuery.data?.data || []
  const profiles = profilesQuery.data || []
  const analyses = analysesQuery.data || []
  const actions = actionsQuery.data || []
  const sync = syncQuery.data
  const metrics = metricsQuery.data

  async function refresh() {
    await queryClient.invalidateQueries()
  }
  async function syncNow() {
    try { await request('/api/sources/sync', { method: 'POST' }); setNotice('Source sync queued. Progress updates here automatically.'); setTimeout(() => setNotice(''), 5000); await refresh() }
    catch (error) { setNotice(error instanceof Error ? error.message : 'Could not start sync.') }
  }
  async function toggleSync() {
    if (!sync) return
    try { await request('/api/sources/sync/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: !sync.enabled }) }); await refresh() }
    catch (error) { setNotice(error instanceof Error ? error.message : 'Could not update schedule.') }
  }

  async function submitAuth(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setAuthError('')
    const form = new FormData(event.currentTarget)
    const email = String(form.get('email') || '').trim().toLowerCase()
    const password = String(form.get('password') || '')
    if (path === '/signup' && password !== String(form.get('confirm') || '')) { setAuthError('Passwords do not match.'); return }
    try {
      const result = await request<{id:number;name:string;email:string;role:string}>(path === '/signup' ? '/api/auth/register' : '/api/auth/login', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(path === '/signup' ? {name:form.get('name'),email,password} : {email,password})})
      setUser(result)
      if (path === '/admin/login' && result.role !== 'admin') { await request('/api/auth/logout',{method:'POST'}); setUser(null); setAuthError('This account does not have administrator access.'); return }
      window.location.assign(result.role === 'admin' ? '/admin' : '/app')
    } catch(error) { setAuthError(error instanceof Error ? error.message : 'Could not sign in.') }
  }

  async function logout() { await request('/api/auth/logout',{method:'POST'}).catch(()=>{}); setUser(null); window.location.assign('/') }

  if (authLoading && (authPage || isAdmin || path === '/app' || path === '/')) return <div className="auth-screen">Loading your session…</div>
  if (authPage) return <AuthPage path={path} onSubmit={submitAuth} error={authError} />
  if (isAdmin) {
    if (!user) return <AuthPage path="/admin/login" onSubmit={submitAuth} error="Sign in with an administrator account." />
    if (user.role !== 'admin') return <main className="auth-screen"><h1>Administrator access required</h1><button onClick={logout}>Sign out</button></main>
    return <main className="admin-screen"><header><a href="/">Niyam AI</a><div><span>{user.name}</span><button onClick={logout}>Log out</button></div></header><section><div className="auth-eyebrow">ADMINISTRATION</div><h1>Registered users</h1><p>Accounts created through public signup</p><article className="user-count"><span>Total registered users</span><strong>{adminData?.total ?? '—'}</strong></article><div className="admin-controls"><button onClick={()=>{setAuthError('');request<typeof adminData>(`/api/admin/users?limit=50&offset=${adminData?.offset||0}`).then(setAdminData).catch(error=>setAuthError(error.message))}}>Refresh list</button><span>Showing {adminData?.users.length||0} of {adminData?.total||0}</span><button disabled={!adminData||adminData.offset+adminData.limit>=adminData.total} onClick={()=>{const offset=(adminData?.offset||0)+(adminData?.limit||50);request<typeof adminData>(`/api/admin/users?limit=50&offset=${offset}`).then(setAdminData).catch(error=>setAuthError(error.message))}}>Next page</button></div>{authError&&<p className="auth-error">{authError}</p>}<div className="user-table"><table><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Registered</th></tr></thead><tbody>{adminData?.users.map(row=><tr key={row.id}><td>{row.name}</td><td>{row.email}</td><td>{row.role}</td><td>{new Date(row.created_at).toLocaleDateString()}</td></tr>)}</tbody></table>{adminData?.users.length===0&&<p>No users registered yet.</p>}</div></section></main>
  }
  if (path === '/app' && !user) return <AuthPage path="/signin" onSubmit={submitAuth} error="Sign in to open your workspace." />
  if (path === '/' && !user && !appEntered) return <LandingPage onAnalyze={() => window.location.assign('/signup')} />
  if (path === '/' && user) { window.location.replace(user.role === 'admin' ? '/admin' : '/app'); return null }
  if (path !== '/app' && path !== '/' && !appEntered) return <LandingPage onAnalyze={() => window.location.assign('/signup')} />

  const titles: Record<Page, string> = { Overview: 'Good morning', Sources: 'Regulatory sources', 'Document library': 'Document library', Compare: 'Compare regulations', 'SME profiles': 'Business profiles', 'Action center': 'Action center', Reports: 'Analysis reports' }
  const subtitles: Record<Page, string> = { Overview: 'Your compliance picture, at a glance.', Sources: 'Monitor connections and document synchronization.', 'Document library': 'Published documents and their processing history.', Compare: 'Review what changed and how it may affect your business.', 'SME profiles': 'Business context used to assess regulatory scope.', 'Action center': 'Track follow-up work from your regulatory reviews.', Reports: 'Saved impact analyses with traceable source evidence.' }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><Landmark size={19} /></div><div><strong>niam<span>ai</span></strong><small>REGULATORY INTELLIGENCE</small></div></div>
      <div className="workspace-select"><span className="workspace-avatar">N</span><span className="workspace-copy"><strong>Niam workspace</strong><small>Business plan</small></span><ChevronDown size={15} /></div>
      {['WORKSPACE', 'MANAGE'].map(group => <div className="nav-group" key={group}><div className="nav-label">{group}</div>{nav.filter(item => item.group === group).map(item => <button key={item.name} aria-label={item.name} title={item.name} onClick={() => { setPage(item.name); setReportId(null) }} className={`nav-item ${page === item.name ? 'selected' : ''}`}><item.icon size={17} strokeWidth={1.8} /><span>{item.name}</span>{item.name === 'Action center' && actions.filter(action => action.status !== 'Completed').length > 0 && <b className="nav-count">{actions.filter(action => action.status !== 'Completed').length}</b>}</button>)}</div>)}
      <div className="sidebar-spacer" />
      <div className="sidebar-sync"><span className={`sync-dot ${sync?.running ? 'pulse' : ''}`} /><div><strong>{sync?.running ? 'Sync in progress' : 'Source monitoring'}</strong><small>{sync?.enabled ? `Every ${sync.interval_minutes} minutes` : 'Scheduled sync paused'}</small></div><button title="Open source settings" onClick={() => setPage('Sources')}><SlidersHorizontal size={15} /></button></div>
      <button className="help-link"><CircleHelp size={16} /> Help & support</button>
      <button className="user-row" onClick={logout}><div className="user-avatar">{user?.name.slice(0,2).toUpperCase()}</div><div><strong>{user?.name || 'Account'}</strong><small>{user?.email || ''} · Sign out</small></div><ChevronDown size={15} /></button>
    </aside>
    <main className="main-panel">
      <header className="topbar"><div className="breadcrumb">Niam workspace <span>/</span> <b>{page}</b></div><div className="top-actions"><span className="today"><Clock3 size={14} /> {new Date().toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}</span><button className="icon-button" title="Notifications" onClick={() => setNotice('No new notifications. Sync results and failed document alerts appear here.')}><Bell size={17} /></button><div className="top-avatar">AK</div></div></header>
      <div className="content-wrap"><div className="page-heading"><div><div className="eyebrow">REGULATORY INTELLIGENCE</div><h1>{reportId ? 'Evidence-backed analysis' : titles[page]}{page === 'Overview' && <span className="heading-period">, team</span>}</h1><p>{reportId ? 'Source clauses, business scope, and next steps.' : subtitles[page]}</p></div>{page === 'Overview' && <button className="button primary" onClick={() => setPage('Compare')}><Plus size={16} /> New analysis</button>}</div>
        {notice && <div className="notice"><span>{notice}</span><button onClick={() => setNotice('')}><X size={16} /></button></div>}
        {(docsQuery.isError || profilesQuery.isError || analysesQuery.isError || syncQuery.isError || metricsQuery.isError) && <div className="error-banner"><ShieldCheck size={17} /><span>API unavailable. Start the FastAPI service to load live workspace data.</span><a href={`${API}/docs`} target="_blank" rel="noreferrer">API status</a></div>}
        {reportId ? <ReportView id={reportId} onBack={() => setReportId(null)} /> : <>
          {page === 'Overview' && <Overview analyses={analyses} actions={actions} profiles={profiles} sync={sync} metrics={metrics} range={dashboardRange} setRange={setDashboardRange} onSync={syncNow} onOpen={setReportId} onNavigate={setPage} onCompare={() => setPage('Compare')} />}
          {page === 'Sources' && <Sources sync={sync} onSync={syncNow} onToggle={toggleSync} />}
          {page === 'Document library' && <DocumentLibrary docs={docs} search={search} setSearch={value => { setSearch(value); setDocumentOffset(0) }} status={documentStatus} setStatus={value => { setDocumentStatus(value); setDocumentOffset(0) }} offset={documentOffset} setOffset={setDocumentOffset} sort={documentSort} setSort={setDocumentSort} onRefresh={refresh} onCompare={() => setPage('Compare')} />}
          {page === 'Compare' && <Compare docs={docs} profiles={profiles} onDone={async id => { await refresh(); if (id) setReportId(id) }} />}
          {page === 'SME profiles' && <Profiles profiles={profiles} refresh={refresh} />}
          {page === 'Action center' && <ActionCenter actions={actions} profiles={profiles} docs={docs} refresh={refresh} />}
          {page === 'Reports' && <Reports onOpen={setReportId} />}
        </>}
        <footer className="footer"><span>NIAM AI <i>•</i> REGULATORY CHANGE INTELLIGENCE</span><span>Decision support, not legal advice</span></footer>
      </div>
    </main>
  </div>
}

function AuthPage({path,onSubmit,error}:{path:string;onSubmit:(event:React.FormEvent<HTMLFormElement>)=>void;error:string}) {
  const signup=path==='/signup'
  const admin=path==='/admin/login'
  return <main className="auth-screen"><a className="auth-brand" href="/">◈ NIYAM AI</a><section className="auth-card"><div className="auth-eyebrow">{admin?'SECURE ADMIN ACCESS':'REGULATORY INTELLIGENCE FOR SMES'}</div><h1>{signup?'Create your account':admin?'Administrator sign in':'Welcome back'}</h1><p>{signup?'Create a workspace to review regulatory changes and evidence.':'Sign in to continue to your Niyam AI workspace.'}</p>{admin&&<div className="admin-setup-note">First administrator setup: create an account with your configured admin email, then promote it using the local bootstrap command in the project README. Admin access is never assigned automatically.</div>}<form onSubmit={onSubmit}>{signup&&<label>Full name<input name="name" autoComplete="name" required maxLength={160}/></label>}<label>Email<input name="email" type="email" autoComplete="email" required/></label><label>Password<input name="password" type="password" autoComplete={signup?'new-password':'current-password'} minLength={signup?10:1} maxLength={128} required/>{signup&&<small>Use at least 10 characters.</small>}</label>{signup&&<label>Confirm password<input name="confirm" type="password" autoComplete="new-password" minLength={10} required/></label>}{error&&<div className="auth-error" role="alert">{error}</div>}<button className="auth-submit">{signup?'Create account':'Sign in'}</button></form><div className="auth-switch">{signup?<>Already registered? <a href="/signin">Sign in</a></>:<>New to Niyam AI? <a href="/signup">Create an account</a></>}</div>{!admin&&<a className="auth-admin-link" href="/admin/login">Administrator sign in</a>}</section></main>
}

function Overview({ analyses, actions, profiles, sync, metrics, range, setRange, onSync, onOpen, onNavigate, onCompare }: { analyses: Analysis[]; actions: Action[]; profiles: Profile[]; sync?: Sync; metrics?: DashboardMetrics; range: 'all' | '30d'; setRange: (range: 'all' | '30d') => void; onSync: () => void; onOpen: (id: number) => void; onNavigate: (page: Page) => void; onCompare: () => void }) {
  const [profileId, setProfileId] = useState('')
  const recent = analyses.slice(0, 4)
  const impactQuery = useQuery({ queryKey: ['dashboard-impact', profileId], queryFn: () => request<DashboardImpact>(`/api/dashboard/impact?profile_id=${profileId}`), enabled: !!profileId })
  const impact = impactQuery.data
  return <>
    <div className="dashboard-range"><span>Activity period</span><div className="range-switch"><button className={range === '30d' ? 'selected' : ''} onClick={() => setRange('30d')}>30 days</button><button className={range === 'all' ? 'selected' : ''} onClick={() => setRange('all')}>All time</button></div></div>
    <section className="panel dashboard-impact">
      <div className="panel-head impact-head"><div><h2>Business impact brief</h2><p>Latest saved comparison, assessed against one SME profile</p></div><label className="impact-profile">BUSINESS PROFILE<select value={profileId} onChange={event => setProfileId(event.target.value)}><option value="">Select a saved profile</option>{profiles.map(profile => <option key={profile.id} value={profile.id}>{profile.name} · {profile.industry}</option>)}</select></label></div>
      {!profileId ? <div className="empty-line">Select a business profile to see its latest changes and next steps.</div> : impactQuery.isLoading ? <div className="empty-line">Loading the latest profile-specific assessment…</div> : impactQuery.isError ? <div className="empty-line">Could not load the profile assessment.</div> : impact && <>
        <div className="impact-answers"><article><span>WHAT CHANGED?</span><p>{impact.what_changed}</p>{impact.source_title && <small>{impact.source_title}</small>}</article><article><span>HOW DOES IT AFFECT THIS BUSINESS?</span><p>{impact.business_impact}</p><small>{impact.findings.length} meaningful clause finding{impact.findings.length === 1 ? '' : 's'} · {impact.profile.name}</small></article><article><span>BY WHEN MUST THE BUSINESS ACT?</span><p>{impact.deadline ? new Date(`${impact.deadline}T00:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' }) : 'No verified compliance deadline stated'}</p><small>{impact.deadline_status === 'VERIFIED' ? 'Source-verified compliance deadline' : 'Effective dates are not treated as filing deadlines'}</small></article></div>
        <div className="impact-action"><div><span>NEXT ACTION</span><p>{impact.required_action}</p></div>{impact.analysis_id && <button className="button secondary" onClick={() => onOpen(impact.analysis_id!)}>Open evidence report <ArrowDownToLine size={14} /></button>}</div>
        {!!impact.findings.length && <div className="impact-finding-list">{impact.findings.slice(0, 3).map(finding => <div className="impact-finding" key={finding.change_id}><div><strong>{finding.category}</strong><span>{finding.applicability.replaceAll('_', ' ')}</span></div><p>{finding.summary}</p><small>{finding.evidence.filter(item => item.verified).map(item => `${item.source_role} source · p. ${item.page_number}${item.clause_id ? ` · ${item.clause_id}` : ''}`).join(' / ') || 'Source citation requires review'}</small></div>)}</div>}
      </>}
    </section>
    <section className="overview-grid">
      <Metric label="Regulatory records" value={metrics?.regulatory_records ?? 0} detail={`${metrics?.document_versions ?? 0} stored versions`} icon={Landmark} color="mint" onClick={() => onNavigate('Document library')} />
      <Metric label="Detected changes" value={metrics?.detected_changes ?? 0} detail="From version comparisons" icon={ArrowLeftRight} color="blue" onClick={() => onNavigate('Reports')} />
      <Metric label="Open actions" value={metrics?.open_actions ?? 0} detail={`${metrics?.upcoming_verified_deadlines ?? 0} verified upcoming deadlines`} icon={Check} color="coral" onClick={() => onNavigate('Action center')} />
      <Metric label="Needs verification" value={metrics?.verification_needed ?? 0} detail={`${metrics?.failed_ingestion_or_analysis_jobs ?? 0} failed jobs`} icon={ShieldCheck} color="yellow" onClick={() => onNavigate('Reports')} />
    </section>
    <section className="overview-grid secondary-metrics">
      <Metric label="Applicable changes" value={metrics?.applicable_changes ?? 0} detail="Per-change assessments" icon={ShieldCheck} color="mint" onClick={() => onNavigate('Reports')} />
      <Metric label="Not applicable" value={metrics?.not_applicable_changes ?? 0} detail="Evidence-supported exclusions" icon={CircleHelp} color="blue" onClick={() => onNavigate('Reports')} />
      <Metric label="Saved analyses" value={metrics?.recent_completed_analyses ?? 0} detail="Persisted reports" icon={FileText} color="coral" onClick={() => onNavigate('Reports')} />
      <Metric label="Source versions" value={metrics?.document_versions ?? 0} detail="Across monitored records" icon={BookOpen} color="yellow" onClick={() => onNavigate('Document library')} />
    </section>
    {!!metrics && <section className="dashboard-columns chart-row"><div className="panel chart-panel"><div className="panel-head"><div><h2>Changes over time</h2><p>Detected findings by analysis month</p></div></div>{(metrics.changes_over_time || []).length ? <ResponsiveContainer width="100%" height={190}><BarChart data={metrics.changes_over_time || []} margin={{ top: 8, right: 10, bottom: 0, left: -18 }}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="month" tick={{ fontSize: 9 }} /><YAxis allowDecimals={false} tick={{ fontSize: 9 }} /><Tooltip /><Bar dataKey="count" radius={[4, 4, 0, 0]} fill="#337f73" /></BarChart></ResponsiveContainer> : <div className="empty-line">No comparison findings yet.</div>}</div><div className="panel chart-panel"><div className="panel-head"><div><h2>Changes by applicability</h2><p>Per-change assessments across comparisons</p></div></div>{metrics.detected_changes ? <ResponsiveContainer width="100%" height={190}><PieChart><Pie data={metrics.changes_by_applicability || []} dataKey="count" nameKey="applicability" innerRadius={48} outerRadius={72} paddingAngle={3}>{(metrics.changes_by_applicability || []).map((item, index) => <Cell key={item.applicability} fill={['#29826f', '#6c91b9', '#bd9147'][index]} />)}</Pie><Tooltip /></PieChart></ResponsiveContainer> : <div className="empty-line">No comparison findings yet.</div>}</div><div className="panel chart-panel"><div className="panel-head"><div><h2>Changes by category</h2><p>Clause-level change classification</p></div></div>{(metrics.changes_by_category || []).length ? <ResponsiveContainer width="100%" height={190}><BarChart data={metrics.changes_by_category || []} margin={{ top: 8, right: 8, bottom: 0, left: 10 }} layout="vertical"><CartesianGrid strokeDasharray="3 3" horizontal={false} /><XAxis type="number" allowDecimals={false} tick={{ fontSize: 9 }} /><YAxis type="category" dataKey="category" width={130} tick={{ fontSize: 8 }} /><Tooltip /><Bar dataKey="count" radius={[0, 4, 4, 0]} fill="#6485a5" /></BarChart></ResponsiveContainer> : <div className="empty-line">No category data yet.</div>}</div><div className="panel chart-panel"><div className="panel-head"><div><h2>Open actions by priority</h2><p>Based on finding category and scope evidence</p></div></div>{metrics.open_actions ? <ResponsiveContainer width="100%" height={190}><BarChart data={metrics.actions_by_priority || []} margin={{ top: 8, right: 10, bottom: 0, left: -18 }}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="priority" tick={{ fontSize: 10 }} /><YAxis allowDecimals={false} tick={{ fontSize: 9 }} /><Tooltip /><Bar dataKey="count" radius={[4, 4, 0, 0]} fill="#337f73" /></BarChart></ResponsiveContainer> : <div className="empty-line">No open actions yet.</div>}</div></section>}
    <section className="dashboard-columns">
      <div className="panel recent-panel"><div className="panel-head"><div><h2>Recent analyses</h2><p>Latest regulatory comparisons</p></div><button className="text-button" onClick={() => onOpen(recent[0]?.id)} disabled={!recent.length}>View latest <span>→</span></button></div>
        {recent.length ? <div className="analysis-list">{recent.map((analysis, index) => <button className="analysis-row" key={analysis.id} onClick={() => onOpen(analysis.id)}><div className={`analysis-icon tone-${index % 3}`}><ArrowLeftRight size={16} /></div><div className="analysis-main"><strong>{analysis.new_title}</strong><span>Compared with {analysis.old_title}</span></div><span className={`pill ${analysis.applicability?.outcome === 'APPLICABLE' ? 'pill-green' : 'pill-amber'}`}>{analysis.applicability?.outcome === 'APPLICABLE' ? 'Applicable' : 'Verify scope'}</span><time>{new Date(analysis.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}</time></button>)}</div> : <Empty icon={ArrowLeftRight} title="No analyses yet" text="Compare two versions or upload PDFs to see business-specific impact." action="Start an analysis" onClick={onCompare} />}
      </div>
      <div className="panel sync-panel"><div className="panel-head"><div><h2>Source monitoring</h2><p>Regulatory Source Portal</p></div><span className={`status-dot ${sync?.enabled ? 'online' : 'offline'}`} /></div>
        <div className="connection"><span className="connection-mark"><Landmark size={18} /></span><div><strong>{sync?.running ? 'Syncing public records' : sync?.enabled ? 'Scheduled monitoring on' : 'Monitoring paused'}</strong><span>Checks every {sync?.interval_minutes || 5} minutes</span></div></div>
        <div className="sync-counts"><div><b>{sync?.latest?.discovered ?? '—'}</b><span>Discovered</span></div><div><b>{sync?.latest?.downloaded ?? '—'}</b><span>Downloaded</span></div><div><b>{sync?.latest?.failed ?? '—'}</b><span>Failed</span></div></div>
        <div className="sync-bottom"><span>{sync?.latest?.finished_at ? `Last run ${new Date(sync.latest.finished_at).toLocaleString('en-IN')}` : 'No completed sync yet'}</span><button className="button primary small" onClick={onSync} disabled={sync?.running}>{sync?.running ? <LoaderCircle className="spin" size={14} /> : <RefreshCw size={14} />} Sync now</button></div>
        {sync?.latest?.detail && <div className="inline-error">{sync.latest.detail}</div>}
      </div>
    </section>
    <section className="panel action-preview"><div className="panel-head"><div><h2>Priority actions</h2><p>Items needing attention</p></div><span className="quiet-count">{actions.filter(action => action.status !== 'Completed').length} open</span></div>{actions.filter(action => action.status !== 'Completed').slice(0, 3).map(action => <ActionRow key={action.id} action={action} onUpdate={() => undefined} editable={false} />)}{!actions.length && <div className="empty-line">No action items yet. New actions appear after a document comparison.</div>}</section>
  </>
}

function Metric({ label, value, detail, icon: Icon, color, onClick }: { label: string; value: number; detail: string; icon: typeof FileText; color: string; onClick: () => void }) {
  return <button className="metric metric-button" onClick={onClick}><div className="metric-top"><span>{label}</span><i className={`metric-icon ${color}`}><Icon size={17} /></i></div><strong className="metric-value">{value}</strong><div className="metric-detail">{detail}</div></button>
}

function Sources({ sync, onSync, onToggle }: { sync?: Sync; onSync: () => void; onToggle: () => void }) {
  const history = useQuery({ queryKey: ['sync-history'], queryFn: () => request<SyncRun[]>('/api/sources/sync/history'), refetchInterval: 8000 }).data || []
  const src = useQuery({ queryKey: ['sources'], queryFn: () => request<{ name: string; url: string; connectivity: string }[]>('/api/sources') }).data?.[0]
  return <div className="section-stack"><div className="panel source-card"><div className="source-title"><div className="source-emblem"><Landmark size={20} /></div><div><h2>{src?.name || 'Regulatory Source Portal'}</h2><a href={src?.url || 'https://regulatory-source-portal.vercel.app/regulations'} target="_blank" rel="noreferrer">{src?.url || 'regulatory-source-portal.vercel.app/regulations'} <ArrowDownToLine size={12} /></a></div><span className="source-connected"><i />{sync?.latest?.status?.startsWith('COMPLETED') ? 'Connected' : src?.connectivity || 'Awaiting first sync'}</span></div>
    <p className="source-note">Public source listing uses a paginated JSON endpoint. Published documents are downloaded from signed links and checked against the source SHA-256 when available.</p><div className="source-controls"><div className="control-copy"><strong>Automatic synchronization</strong><span>Background worker checks for newly published versions.</span></div><button className={`switch ${sync?.enabled ? 'on' : ''}`} role="switch" aria-checked={sync?.enabled || false} onClick={onToggle}><i /></button><button className="button primary" onClick={onSync} disabled={sync?.running}>{sync?.running ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />} Sync now</button></div>
    <div className="source-stats"><div><span>Cadence</span><strong>{sync?.interval_minutes || 5} minutes</strong></div><div><span>Last successful sync</span><strong>{sync?.latest?.finished_at ? new Date(sync.latest.finished_at).toLocaleString('en-IN') : 'Not yet run'}</strong></div><div><span>Next scheduled sync</span><strong>{sync?.next_sync ? new Date(sync.next_sync).toLocaleString('en-IN') : sync?.enabled ? 'Scheduler starting' : 'Paused'}</strong></div></div>
    <div className="last-result"><span>Latest run</span><div><b>{sync?.latest?.discovered ?? 0} discovered</b><b>{sync?.latest?.downloaded ?? 0} downloaded</b><b>{sync?.latest?.skipped ?? 0} unchanged</b><b>{sync?.latest?.updated ?? 0} versions updated</b><b className={sync?.latest?.failed ? 'red-text' : ''}>{sync?.latest?.failed ?? 0} failed</b></div></div>
  </div><div className="panel"><div className="panel-head"><div><h2>Synchronization history</h2><p>Recent source checks and processing outcomes</p></div></div>{history.length ? <div className="history-list">{history.map((run, index) => run && <div className="history-row" key={`${run.started_at}-${index}`}><span className={`history-state ${run.status === 'FAILED' ? 'failed' : ''}`}><i />{run.status.replaceAll('_', ' ')}</span><span>{run.discovered} discovered</span><span>{run.downloaded} downloaded</span><span>{run.failed} failed</span><time>{run.finished_at ? new Date(run.finished_at).toLocaleString('en-IN') : 'In progress'}</time></div>)}</div> : <div className="empty-line">Sync history will appear after the first run.</div>}</div></div>
}

function DocumentLibrary({ docs, search, setSearch, status, setStatus, offset, setOffset, sort, setSort, onRefresh, onCompare }: { docs: Doc[]; search: string; setSearch: (value: string) => void; status: string; setStatus: (value: string) => void; offset: number; setOffset: (value: number) => void; sort: string; setSort: (value: string) => void; onRefresh: () => void; onCompare: () => void }) {
  const [retrying, setRetrying] = useState<number | null>(null)
  const [message, setMessage] = useState('')
  async function retry(id: number) {
    setRetrying(id); setMessage('')
    try { await request(`/api/regulations/${id}/retry`, { method: 'POST' }); setMessage('Retry queued. Status will update automatically.') }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Retry could not be queued.') }
    finally { setRetrying(null) }
  }
  const sortedDocs = [...docs].sort((left, right) => sort === 'title' ? left.title.localeCompare(right.title) : 0)
  return <div className="panel table-panel"><div className="table-toolbar"><div className="search-field"><Search size={16} /><input placeholder="Search title or authority" value={search} onChange={event => setSearch(event.target.value)} /></div><select className="filter-select" aria-label="Filter document status" value={status} onChange={event => setStatus(event.target.value)}><option value="">All statuses</option><option>DISCOVERED</option><option>EXTRACTED</option><option>FAILED</option><option>NEEDS_REVIEW</option></select><select className="filter-select" aria-label="Sort documents" value={sort} onChange={event => setSort(event.target.value)}><option value="recent">Recently retrieved</option><option value="title">Title A–Z</option></select><button className="button secondary" onClick={onRefresh}><RefreshCw size={15} /> Refresh</button><button className="button primary" onClick={onCompare}><ArrowLeftRight size={15} /> Compare documents</button></div>
    {message && <div className="notice"><span>{message}</span><button onClick={() => setMessage('')}><X size={16} /></button></div>}
    <div className="table-scroll"><table><thead><tr><th>REGULATION</th><th>ISSUING AUTHORITY</th><th>JURISDICTION</th><th>PUBLICATION</th><th>VERSION</th><th>STATUS</th><th /></tr></thead><tbody>{sortedDocs.map(doc => <tr key={doc.id}><td><strong>{doc.title}</strong><span>{doc.category}{doc.industry ? ` · ${doc.industry}` : ''}</span>{doc.error && <small className="red-text">{doc.error}</small>}</td><td>{doc.authority}</td><td>{doc.jurisdiction || '—'}</td><td>{doc.publication_date || '—'}{doc.effective_date && <small>Effective {doc.effective_date}</small>}</td><td>{doc.version_label || '—'}</td><td><span className={`state-pill ${doc.status.toLowerCase()}`}>{doc.status}</span></td><td>{doc.status === 'FAILED' ? <button className="icon-link" title="Retry failed document" onClick={() => retry(doc.id)} disabled={retrying === doc.id}>{retrying === doc.id ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />}</button> : <a className="icon-link" href={`${API}/api/regulations/${doc.id}/download`} title="Download source PDF" target="_blank" rel="noreferrer"><ArrowDownToLine size={16} /></a>}</td></tr>)}</tbody></table></div>
    {!docs.length && <Empty icon={FileText} title="No documents stored" text="Run source synchronization to discover and process published regulations." action="" />}
    <div className="table-footer"><span>Showing {docs.length ? offset + 1 : 0}–{offset + docs.length} documents</span><span className="pagination"><button className="button secondary small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous</button><button className="button secondary small" disabled={docs.length < 25} onClick={() => setOffset(offset + 25)}>Next</button></span></div>
  </div>
}

function Compare({ docs, profiles, onDone }: { docs: Doc[]; profiles: Profile[]; onDone: (id?: number) => void }) {
  const [mode, setMode] = useState<'library' | 'upload'>('library')
  const [workflow, setWorkflow] = useState<'compare' | 'current'>('compare')
  const [oldId, setOldId] = useState('')
  const [newId, setNewId] = useState('')
  const [profileId, setProfileId] = useState('')
  const [oldFile, setOldFile] = useState<File | null>(null)
  const [newFile, setNewFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit() {
    setBusy(true); setError('')
    try {
      let result: { id: number }
      if (mode === 'library') {
        if (!profileId) throw new Error('Select a saved SME profile first.')
        if (workflow === 'current') {
          if (!newId) throw new Error('Choose a current regulatory document.')
          const body = new FormData(); body.append('profile_id', profileId)
          result = await request(`/api/regulations/${newId}/analyze`, { method: 'POST', body })
        } else {
          if (!oldId || !newId || oldId === newId) throw new Error('Choose two distinct document versions.')
          const body = new FormData(); body.append('old_id', oldId); body.append('new_id', newId); body.append('profile_id', profileId)
          result = await request('/api/documents/compare', { method: 'POST', body })
        }
      } else {
        if (!profileId) throw new Error('Select a saved SME profile first.')
        if (!oldFile || !newFile) throw new Error('Select both a previous and updated PDF.')
        const body = new FormData(); body.append('old_pdf', oldFile); body.append('new_pdf', newFile); if (profileId) body.append('profile_id', profileId)
        result = await request('/api/documents/upload', { method: 'POST', body })
      }
      onDone(result.id)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Comparison could not be completed.') }
    finally { setBusy(false) }
  }
  return <div className="compare-layout"><div className="panel compare-main"><div className="segment"><button className={mode === 'library' ? 'active' : ''} onClick={() => setMode('library')}><BookOpen size={15} /> Existing documents</button><button className={mode === 'upload' ? 'active' : ''} onClick={() => setMode('upload')}><Upload size={15} /> Upload PDFs</button></div>
    {mode === 'library' ? <><div className="workflow-switch"><button className={workflow === 'compare' ? 'selected' : ''} onClick={() => setWorkflow('compare')}><ArrowLeftRight size={14} /> Compare verified versions</button><button className={workflow === 'current' ? 'selected' : ''} onClick={() => setWorkflow('current')}><ShieldCheck size={14} /> Assess current version</button></div>{workflow === 'compare' ? <><div className="compare-selectors"><DocumentSelect label="PREVIOUS VERSION" value={oldId} onChange={setOldId} docs={docs} emptyLabel="Select previous version" /><div className="compare-connector"><ArrowLeftRight size={17} /></div><DocumentSelect label="UPDATED VERSION" value={newId} onChange={setNewId} docs={docs} emptyLabel="Select updated version" /></div><div className="inline-note"><CircleHelp size={16} /> Backend verifies that the updated version explicitly links to the selected previous version. Distinct regulatory records cannot be compared as amendments.</div></> : <><DocumentSelect label="CURRENT REGULATORY DOCUMENT" value={newId} onChange={setNewId} docs={docs} emptyLabel="Select a current document" /><div className="inline-note"><CircleHelp size={16} /> Assesses current clauses against your profile. No historical comparison is claimed.</div></>}</> : <div className="upload-pair"><FileDrop label="Previous version" file={oldFile} onFile={setOldFile} /><FileDrop label="Updated version" file={newFile} onFile={setNewFile} /></div>}
    <label className="form-label profile-picker">BUSINESS PROFILE<select value={profileId} onChange={event => setProfileId(event.target.value)}><option value="">No profile selected</option>{profiles.map(profile => <option value={profile.id} key={profile.id}>{profile.name} · {profile.industry}</option>)}</select></label>
    {error && <div className="form-error">{error}</div>}<div className="compare-footer"><span>Text extraction, clause comparison, and evidence links are included.</span><button className="button primary" onClick={submit} disabled={busy}>{busy ? <LoaderCircle size={16} className="spin" /> : <ArrowLeftRight size={16} />} {busy ? 'Analyzing…' : 'Run comparison'}</button></div>
  </div><aside className="panel method-panel"><div className="method-icon"><ShieldCheck size={20} /></div><h3>Evidence first</h3><p>Original clause text is preserved alongside every detected difference. Uncertain legal meaning is flagged for review.</p><div className="method-step"><i>01</i><span>Extract page text</span></div><div className="method-step"><i>02</i><span>Compare changed lines</span></div><div className="method-step"><i>03</i><span>Assess business scope</span></div><div className="method-step"><i>04</i><span>Build action report</span></div><div className="method-disclaimer">A scan-only PDF needs OCR; this installation reports that clearly and does not invent text.</div></aside></div>
}

function DocumentSelect({ label, value, onChange, docs, emptyLabel }: { label: string; value: string; onChange: (value: string) => void; docs: Doc[]; emptyLabel: string }) {
  return <label className="document-select"><span>{label}</span><select value={value} onChange={event => onChange(event.target.value)}><option value="">{emptyLabel}</option>{docs.map(doc => <option value={doc.id} key={doc.id}>{doc.title} · v{doc.version_label || 'unknown'} · {doc.publication_date || 'date unknown'}</option>)}</select></label>
}
function FileDrop({ label, file, onFile }: { label: string; file: File | null; onFile: (file: File | null) => void }) {
  return <label className={`file-drop ${file ? 'has-file' : ''}`}><input type="file" accept="application/pdf,.pdf" onChange={event => onFile(event.target.files?.[0] || null)} /><span className="file-icon">{file ? <FileText size={20} /> : <FilePlus2 size={20} />}</span><b>{label}</b><span>{file ? file.name : 'Choose a PDF file'}</span><small>PDF only · up to 25 MB</small></label>
}

function Profiles({ profiles, refresh }: { profiles: Profile[]; refresh: () => Promise<void> }) {
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [name, setName] = useState(''); const [industry, setIndustry] = useState(''); const [activities, setActivities] = useState(''); const [state, setState] = useState(''); const [employees, setEmployees] = useState(''); const [turnover, setTurnover] = useState(''); const [registrations, setRegistrations] = useState(''); const [jurisdictions, setJurisdictions] = useState(''); const [facilities, setFacilities] = useState(''); const [error, setError] = useState('')
  function edit(profile: Profile) {
    setEditingId(profile.id); setName(profile.name); setIndustry(profile.industry); setActivities(profile.activities); setState(profile.state); setEmployees(profile.employee_count?.toString() || ''); setTurnover(profile.annual_turnover || ''); setRegistrations(profile.registrations); setJurisdictions(profile.jurisdictions?.join(', ') || ''); setFacilities(profile.facilities?.join(', ') || ''); setShowForm(true); setError('')
  }
  function resetForm() {
    setEditingId(null); setName(''); setIndustry(''); setActivities(''); setState(''); setEmployees(''); setTurnover(''); setRegistrations(''); setJurisdictions(''); setFacilities(''); setShowForm(false); setError('')
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setError('')
    try { await request(editingId ? `/api/business-profiles/${editingId}` : '/api/business-profiles', { method: editingId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, industry, activities, state, employee_count: employees ? Number(employees) : null, annual_turnover: turnover || null, registrations, jurisdictions: jurisdictions.split(',').map(value => value.trim()).filter(Boolean), facilities: facilities.split(',').map(value => value.trim()).filter(Boolean) }) }); resetForm(); await refresh() }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save profile.') }
  }
  return <div className="section-stack"><div className="panel profile-intro"><div className="profile-intro-mark"><Building2 size={21} /></div><div><h2>Business context</h2><p>Profiles are used to assess potential scope. Missing facts result in a verification request rather than a negative conclusion.</p></div><button className="button primary" onClick={() => showForm ? resetForm() : setShowForm(true)}>{showForm ? <X size={15} /> : <Plus size={16} />}{showForm ? 'Cancel' : 'Add profile'}</button></div>
    {showForm && <form className="panel profile-form" onSubmit={submit}><div className="panel-head"><div><h2>{editingId ? 'Edit business profile' : 'New business profile'}</h2><p>Only include facts relevant to your regulatory scope.</p></div></div><div className="form-grid"><label className="form-label">BUSINESS NAME<input required value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Northstar Components" /></label><label className="form-label">INDUSTRY<input required value={industry} onChange={e => setIndustry(e.target.value)} placeholder="e.g. Manufacturing" /></label><label className="form-label wide">BUSINESS ACTIVITIES<textarea value={activities} onChange={e => setActivities(e.target.value)} placeholder="Describe relevant activities" rows={3} /></label><label className="form-label">PRIMARY STATE<input value={state} onChange={e => setState(e.target.value)} placeholder="e.g. Maharashtra" /></label><label className="form-label">EMPLOYEE COUNT<input type="number" min="0" value={employees} onChange={e => setEmployees(e.target.value)} placeholder="Optional" /></label><label className="form-label">ANNUAL TURNOVER<input value={turnover} onChange={e => setTurnover(e.target.value)} placeholder="Optional, include currency/year" /></label><label className="form-label">OPERATING JURISDICTIONS<input value={jurisdictions} onChange={e => setJurisdictions(e.target.value)} placeholder="Comma-separated states" /></label><label className="form-label wide">FACILITIES / OPERATIONS<input value={facilities} onChange={e => setFacilities(e.target.value)} placeholder="e.g. Factory, warehouse, food handling site" /></label><label className="form-label wide">REGISTRATIONS / LICENCES<input value={registrations} onChange={e => setRegistrations(e.target.value)} placeholder="GST, factory licence, etc." /></label></div>{error && <div className="form-error">{error}</div>}<div className="form-actions"><span>Profile data stays in your configured database.</span><button className="button primary">{editingId ? 'Save changes' : 'Save profile'}</button></div></form>}
    <div className="profile-grid">{profiles.map(profile => <article className="panel profile-card" key={profile.id}><div className="profile-card-head"><span className="profile-avatar"><Building2 size={18} /></span><button className="text-button" onClick={() => edit(profile)}>Edit profile</button></div><h3>{profile.name}</h3><p>{profile.industry}</p><div className="profile-facts"><span><b>Location</b>{profile.state || 'Not specified'}</span><span><b>Employees</b>{profile.employee_count ?? 'Not specified'}</span><span><b>Registrations</b>{profile.registrations || 'Not specified'}</span></div></article>)}{!profiles.length && <div className="panel profile-empty"><Building2 size={22} /><strong>No business profiles</strong><span>Add a profile to evaluate regulations against your operations.</span><button className="text-button" onClick={() => setShowForm(true)}>Create the first profile →</button></div>}</div>
  </div>
}

function ActionCenter({ actions, profiles, docs, refresh }: { actions: Action[]; profiles: Profile[]; docs: Doc[]; refresh: () => Promise<void> }) {
  const [status, setStatus] = useState('')
  const [priority, setPriority] = useState('')
  const [profileId, setProfileId] = useState('')
  const [regulationId, setRegulationId] = useState('')
  const queryKey = ['actions-filtered', status, priority, profileId, regulationId]
  const actionQuery = useQuery({ queryKey, queryFn: () => request<Action[]>(`/api/actions?${new URLSearchParams({ ...(status ? { status } : {}), ...(priority ? { priority } : {}), ...(profileId ? { profile_id: profileId } : {}), ...(regulationId ? { regulation_id: regulationId } : {}) })}`) })
  const filtered = actionQuery.data || actions
  async function update(id: number, nextStatus: string, assignedRole?: string) { await request(`/api/actions/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: nextStatus, assigned_role: assignedRole }) }); await refresh(); await actionQuery.refetch() }
  return <div className="panel action-panel"><div className="table-toolbar"><div className="filter-heading"><h2>Compliance actions</h2><span>{filtered.length} shown · persisted</span></div><select className="filter-select" aria-label="Filter action status" value={status} onChange={event => setStatus(event.target.value)}><option value="">All statuses</option><option>Pending</option><option>In progress</option><option>Completed</option><option>Needs review</option></select><select className="filter-select" aria-label="Filter action priority" value={priority} onChange={event => setPriority(event.target.value)}><option value="">All priorities</option><option>High</option><option>Review</option><option>Low</option></select><select className="filter-select" aria-label="Filter business profile" value={profileId} onChange={event => setProfileId(event.target.value)}><option value="">All profiles</option>{profiles.map(profile => <option key={profile.id} value={profile.id}>{profile.name}</option>)}</select><select className="filter-select" aria-label="Filter regulation" value={regulationId} onChange={event => setRegulationId(event.target.value)}><option value="">All regulations</option>{docs.map(doc => <option key={doc.regulation_id} value={doc.regulation_id}>{doc.title}</option>)}</select></div>{filtered.length ? filtered.map(action => <div key={action.id}><ActionRow action={action} onUpdate={next => update(action.id, next, action.assigned_role || undefined)} /><div className="action-meta-row"><span>{action.regulation_id ? `Regulation ${action.regulation_id}` : 'Manual comparison'} · Change {action.change_id || 'unavailable'} · Profile {profiles.find(profile => profile.id === action.profile_id)?.name || 'not recorded'}</span><label>Assigned role<input aria-label={`Assigned role for ${action.title}`} placeholder="Unassigned" defaultValue={action.assigned_role || ''} onBlur={event => { if (event.target.value !== (action.assigned_role || '')) void update(action.id, action.status, event.target.value) }} /></label><a href={`${API}/api/impact-analysis/${action.analysis_id}`}>Open analysis ↗</a></div></div>) : <Empty icon={Check} title="Nothing in this view" text="Actions are generated from saved impact findings and remain linked to their source evidence." action="" />}</div>
}
function ActionRow({ action, onUpdate, editable = true }: { action: Action; onUpdate: (status: string) => void; editable?: boolean }) {
  return <div className="action-row"><span className={`priority-mark ${action.priority.toLowerCase()}`} /><div className="action-copy"><strong>{action.title}</strong><span>{action.description}</span><small>Source evidence: {action.evidence || 'See linked analysis'}</small></div><span className={`priority-label ${action.priority.toLowerCase()}`}>{action.priority}</span><div className="action-due">{action.deadline ? <><b>{action.deadline}</b><span>Verified date</span></> : <><b>No verified date</b><span>Needs review</span></>}</div>{editable && <select className="action-status" aria-label="Action status" value={action.status} onChange={event => onUpdate(event.target.value)}><option>Pending</option><option>In progress</option><option>Completed</option><option>Needs review</option></select>}</div>
}

function Reports({ onOpen }: { onOpen: (id: number) => void }) {
  const [search, setSearch] = useState('')
  const history = useQuery({ queryKey: ['report-history', search], queryFn: () => request<Analysis[]>(`/api/reports?q=${encodeURIComponent(search)}`) }).data || []
  return <div className="panel report-list"><div className="panel-head"><div><h2>Saved analyses</h2><p>Persisted reports with source versions, selected profile, findings, and status.</p></div></div><div className="search-field report-search"><Search size={15} /><input placeholder="Search reports by regulation or profile" value={search} onChange={event => setSearch(event.target.value)} /></div>{history.length ? history.map(analysis => <div className="report-row" key={analysis.id}><span className="report-symbol"><FileText size={18} /></span><div><strong>{analysis.new_title}</strong><span>{analysis.is_comparison ? `Previous: ${analysis.old_title}` : 'Current-version assessment'} · {analysis.profile_name || 'Profile missing'}</span></div><span className="pill pill-amber">{analysis.summary?.counts?.NEEDS_VERIFICATION ?? 0} to verify</span><time>{new Date(analysis.created_at).toLocaleDateString('en-IN')}</time><button className="button secondary small" onClick={() => onOpen(analysis.id)}>Open report</button><a className="icon-link" href={`${API}/api/reports/${analysis.id}/download`} title="Download PDF"><ArrowDownToLine size={17} /></a></div>) : <Empty icon={FileText} title="No saved reports" text="Run a comparison or assess a current-version document." action="" />}</div>
}

function ReportView({ id, onBack }: { id: number; onBack: () => void }) {
  const reportQuery = useQuery({ queryKey: ['report', id], queryFn: () => request<Record<string, any>>(`/api/reports/${id}`) })
  const [tab, setTab] = useState<'findings' | 'actions' | 'context'>('findings')
  const [reviewError, setReviewError] = useState('')
  async function markReviewed(changeId: string, status: string) {
    setReviewError('')
    try { await request(`/api/impact-analysis/${id}/findings/${encodeURIComponent(changeId)}/review`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) }); await reportQuery.refetch() }
    catch (error) { setReviewError(error instanceof Error ? error.message : 'Review status could not be updated.') }
  }
  const report = reportQuery.data
  return <div className="report-detail">{reportQuery.isLoading ? <div className="panel loading-state"><LoaderCircle className="spin" /> Loading report…</div> : report ? <><div className="report-toolbar"><button className="text-button" onClick={onBack}>← Back</button><span className="report-generated">Saved analysis #{id} · {new Date(report.created_at).toLocaleString('en-IN')}</span><a className="button primary" href={`${API}/api/reports/${id}/download`}><ArrowDownToLine size={16} /> Download PDF</a></div>
    <div className="panel result-summary"><div className="result-label">EXECUTIVE SUMMARY · {report.is_comparison ? 'VERSION COMPARISON' : 'CURRENT-VERSION ASSESSMENT'}</div><div className="executive-counts"><SummaryCount value={report.summary?.meaningful_changes ?? report.findings?.length ?? report.changes.length} label="Meaningful changes" /><SummaryCount value={report.summary?.counts?.APPLICABLE ?? 0} label="Applicable" /><SummaryCount value={report.summary?.counts?.NOT_APPLICABLE ?? 0} label="Not applicable" /><SummaryCount value={report.summary?.counts?.NEEDS_VERIFICATION ?? 0} label="Verify scope" /><SummaryCount value={report.findings?.filter((item: Finding) => item.priority === 'High').length ?? 0} label="High priority" /><SummaryCount value={report.findings?.filter((item: Finding) => item.deadline_status === 'VERIFIED').length ?? 0} label="Verified dates" /></div><div className="document-pair"><div><span>PREVIOUS DOCUMENT</span><b>{report.previous_document}</b></div><ArrowLeftRight size={17} /><div><span>{report.is_comparison ? 'UPDATED DOCUMENT' : 'CURRENT DOCUMENT'}</span><b>{report.updated_document}</b></div></div><div className="source-evidence">{['previous', report.is_comparison ? 'updated' : 'current'].map(role => { const source = report.source_versions?.[role]; return source && <div key={role}><span>{role.toUpperCase()} VERSION · SHA-256</span><code>{source.version_id || source.source_id || source.filename} · {(source.content_hash || '').slice(0, 16)} · Published {source.publication_date || 'unknown'} · Effective {source.effective_date || 'unknown'}</code></div> })}</div>{report.profile && <div className="profile-context-line"><Building2 size={14} /> Assessed against <strong>{report.profile.name}</strong> · {report.profile.industry} · {report.profile.state || 'jurisdiction unspecified'} · {report.profile.employee_count ?? 'employee count unknown'} employees</div>}</div>
    <div className="panel result-tabs-panel"><div className="segment result-tabs"><button className={tab === 'findings' ? 'active' : ''} onClick={() => setTab('findings')}>Change findings <span>{report.findings?.length ?? 0}</span></button><button className={tab === 'actions' ? 'active' : ''} onClick={() => setTab('actions')}>Action plan <span>{report.actions?.length ?? 0}</span></button><button className={tab === 'context' ? 'active' : ''} onClick={() => setTab('context')}>Scope & limitations</button></div>{reviewError && <div className="form-error">{reviewError}</div>}
      {tab === 'findings' && (report.findings?.length ? report.findings.map((finding: Finding) => <article className="finding-card" key={finding.change_id}><div className="finding-head"><div><span className="change-category">{finding.category}</span><span className={`applicability-pill ${finding.applicability.toLowerCase()}`}>{finding.applicability.replaceAll('_', ' ')}</span><span className={`review-badge ${finding.priority.toLowerCase()}`}>{finding.priority} priority</span></div><button className="button secondary small" onClick={() => markReviewed(finding.change_id, finding.review_status === 'REVIEWED' ? 'NEEDS_REVIEW' : 'REVIEWED')}>{finding.review_status === 'REVIEWED' ? 'Reopen review' : 'Mark reviewed'}</button></div><h3>{finding.summary}</h3><p className="finding-reason">{finding.applicability_reason}</p><div className="clause-columns"><div className="clause old-clause"><span>PREVIOUS · {finding.previous_text ? 'SOURCE CLAUSE' : 'NOT COMPARED'}</span><p>{finding.previous_text || (report.is_comparison ? 'No previous clause' : 'Historical comparison was not performed.')}</p></div><div className="clause new-clause"><span>{report.is_comparison ? 'UPDATED' : 'CURRENT'} · SOURCE CLAUSE</span><p>{finding.updated_text || 'No updated clause'}</p></div></div><div className="finding-detail-grid"><div><b>Business impact</b><p>{finding.business_impact}</p></div><div><b>Recommended action</b><p>{finding.required_action}</p></div><div><b>Scope conditions</b><p>{finding.applicable_conditions.join(' · ') || 'None directly identified'}</p></div><div><b>Profile matches</b><p>{finding.matching_business_characteristics.join(' · ') || 'No matched profile fact established'}</p></div><div><b>Exemptions</b><p>{finding.exemptions.join(' · ') || 'None verified'}</p></div><div><b>Timing</b><p>Published {finding.publication_date || 'unknown'} · Effective {finding.effective_date || 'unknown'} · Compliance deadline {finding.compliance_deadline || 'unverified'} ({finding.deadline_status})</p></div></div>{(finding.missing_information.length > 0 || finding.follow_up_questions.length > 0) && <div className="finding-uncertainty"><strong>Needs verification</strong>{finding.missing_information.map(item => <span key={item}>{item}</span>)}{finding.follow_up_questions.map(item => <span key={item}>Question: {item}</span>)}</div>}<div className="citation-list"><b>Source evidence</b>{finding.evidence.length ? finding.evidence.map((citation, index) => <div className="citation" key={`${citation.source_role}-${citation.page_number}-${index}`}><span>{citation.document_version_id} · {citation.source_role} · page {citation.page_number}{citation.clause_id ? ` · ${citation.clause_id}` : ''} · {citation.verified ? 'verified quotation' : 'needs review'}</span><q>{citation.quoted_text}</q><a href={`${API}/api/impact-analysis/${id}/evidence/${citation.source_role}/download#page=${citation.page_number}`} target="_blank" rel="noreferrer">Open source page ↗</a></div>) : <span className="form-error">No verified source citation. This finding requires review.</span>}</div></article>) : <div className="empty-line">No per-change findings were saved.</div>)}
      {tab === 'actions' && (report.actions?.length ? report.actions.map((action: any, index: number) => <div className="report-action expanded" key={index}><span className={`priority-mark ${action.priority.toLowerCase()}`} /><div><strong>{action.title}</strong><span>{action.description}</span><small>{action.reason} · {action.deadline ? `Deadline ${action.deadline}` : 'No verified compliance deadline'} · {action.verification_status}</small></div><a className="text-button" href={`${API}/api/reports/${id}`}>Finding {action.change_id}</a></div>) : <div className="empty-line">No actions were generated for this analysis.</div>)}
      {tab === 'context' && <div className="context-content"><h3>Analysis method</h3><p>{report.method}</p><h3>Source limitations</h3><p>Comparisons use extracted text and preserve the page references associated with each difference. Text similarity is not a legal equivalence determination.</p><h3>Review required</h3><p>Verify scope against the full regulation, profile facts, exclusions, transitional provisions, and official source. AI interpretation is decision support only.</p><h3>Follow-up information</h3><p>{report.applicability?.missing_facts?.join(' · ') || report.findings?.flatMap((finding: Finding) => finding.missing_information).join(' · ') || 'No additional facts requested.'}</p></div>}
    </div><p className="disclaimer">{report.disclaimer} · {report.method}</p></> : <div className="panel error-banner">Could not load this report.</div>}</div>
}

function SummaryCount({ value, label }: { value: number; label: string }) { return <div className="summary-count"><b>{value}</b><span>{label}</span></div> }

function Empty({ icon: Icon, title, text, action, onClick }: { icon: typeof FileText; title: string; text: string; action: string; onClick?: () => void }) {
  return <div className="empty-state"><span><Icon size={20} /></span><strong>{title}</strong><p>{text}</p>{action && <button className="text-button" onClick={onClick}>{action} →</button>}</div>
}
