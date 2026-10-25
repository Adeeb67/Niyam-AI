import { useState } from 'react'
import { ArrowDownRight, ArrowLeftRight, ArrowRight, Bell, Building2, CalendarClock, Check, CheckCircle2, ChevronDown, CircleHelp, ClipboardCheck, FileSearch, FileText, GitCompareArrows, Menu, Shield, ShieldCheck, Sparkles, X } from 'lucide-react'
import './landing.css'

type LandingPageProps = { onAnalyze: () => void }
type DemoChange = { title: string; oldText: string; newText: string; impact: string; applicability: string; action: string; date: string; clause: string }

const features = [
  { icon: FileSearch, title: 'Regulatory Change Detection', description: 'Track new regulations, amendments, circulars, and official notifications in one place.', note: 'CHANGE TRACKING' },
  { icon: Building2, title: 'Business Applicability', description: 'Assess potential applicability using the SME’s industry, jurisdiction, size, and activities.', note: 'BUSINESS CONTEXT' },
  { icon: GitCompareArrows, title: 'Before vs. After Analysis', description: 'Identify provisions that were added, removed, renumbered, or materially changed.', note: 'SIDE-BY-SIDE COMPARISON' },
  { icon: CalendarClock, title: 'Deadline Intelligence', description: 'Separate stated effective dates from compliance deadlines, with source references.', note: 'DATE EVIDENCE' },
  { icon: ShieldCheck, title: 'Readiness & Risk Insights', description: 'See potential impact, missing information, and areas that need human review.', note: 'REVIEW SUPPORT' },
  { icon: ClipboardCheck, title: 'Action Plans & Timeline', description: 'Turn relevant changes into prioritized next steps and a trackable follow-up plan.', note: 'NEXT STEPS' },
]

const workflow = [
  { title: 'Collect', detail: 'Retrieve a published document or upload a PDF.', icon: FileText },
  { title: 'Extract', detail: 'Read clause text and keep page-level references.', icon: FileSearch },
  { title: 'Compare', detail: 'Match earlier and updated provisions.', icon: ArrowLeftRight },
  { title: 'Assess', detail: 'Review changes against an SME profile.', icon: Building2 },
  { title: 'Act', detail: 'Use evidence, recommendations, and dates to plan follow-up.', icon: CheckCircle2 },
]

const demoChanges: DemoChange[] = [
  { title: 'Register filing frequency', oldText: 'Covered entities shall submit the register annually.', newText: 'Covered entities shall submit the register quarterly.', impact: 'The register workflow may need four scheduled submissions instead of one.', applicability: 'Needs Verification', action: 'Confirm the entity is in scope, then assign an owner and add quarterly dates to the compliance calendar.', date: 'No separate filing deadline stated in this sample.', clause: 'Illustrative Clause 4 · page 3' },
  { title: 'Employee eligibility threshold', oldText: 'This provision applies to businesses with 100 or more employees.', newText: 'This provision applies to businesses with 50 or more employees.', impact: 'Smaller businesses may now fall within the provision’s stated scope.', applicability: 'Potentially Applicable', action: 'Check the employee count and measurement period against the official instrument before deciding applicability.', date: 'Example effective date: 1 January 2027.', clause: 'Illustrative Clause 7 · page 5' },
  { title: 'Record retention period', oldText: 'Supporting records must be retained for 2 years.', newText: 'Supporting records must be retained for 5 years.', impact: 'The records policy and storage plan may need to cover a longer period.', applicability: 'Needs Verification', action: 'Confirm the record types in scope and update the retention schedule after review.', date: 'No separate filing deadline stated in this sample.', clause: 'Illustrative Clause 9 · page 8' },
]

function Logo() {
  return <a className="landing-brand" href="#top" aria-label="Niyam AI home"><span className="landing-brand-mark"><ShieldCheck size={21} strokeWidth={2.2} /></span><span className="landing-brand-type"><strong>Niyam AI</strong><small>REGULATORY INTELLIGENCE</small></span></a>
}

export default function LandingPage({ onAnalyze }: LandingPageProps) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [authMessage, setAuthMessage] = useState('')
  const [demoIndex, setDemoIndex] = useState(0)
  const [expanded, setExpanded] = useState(true)
  const currentDemo = demoChanges[demoIndex]

  function showAuthPlaceholder(which: string) { setMenuOpen(false); window.location.assign(which.toLowerCase().includes('admin') ? '/admin/login' : '/signin') }

  function closeMenu() { setMenuOpen(false) }

  return <div className="landing" id="top">
    <header className="landing-header">
      <div className="landing-nav-wrap">
        <Logo />
        <nav className={`landing-nav ${menuOpen ? 'is-open' : ''}`} aria-label="Main navigation">
          <a href="#features" onClick={closeMenu}>Features</a>
          <a href="#how-it-works" onClick={closeMenu}>How it works</a>
          <a href="#product-preview" onClick={closeMenu}>Product preview</a>
          <div className="mobile-nav-actions">
            <button onClick={() => showAuthPlaceholder('Admin login')}>Admin login</button>
            <button onClick={() => showAuthPlaceholder('Sign in')}>Sign in</button>
            <button className="mobile-get-started" onClick={() => { closeMenu(); window.location.assign('/signup') }}>Get started <ArrowRight size={15} /></button>
          </div>
        </nav>
        <div className="landing-auth-links"><button onClick={() => showAuthPlaceholder('Admin login')}>Admin Login</button><button onClick={() => showAuthPlaceholder('Sign in')}>Sign in</button></div>
        <button className="landing-get-started" onClick={() => window.location.assign('/signup')}>Get started <ArrowRight size={16} /></button>
        <button className="landing-menu-toggle" aria-label={menuOpen ? 'Close navigation menu' : 'Open navigation menu'} aria-expanded={menuOpen} onClick={() => setMenuOpen(value => !value)}>{menuOpen ? <X size={21} /> : <Menu size={21} />}</button>
      </div>
    </header>

    <main>
      <section className="landing-hero">
        <div className="hero-copy reveal-up">
          <a className="hero-eyebrow" href="#features"><Sparkles size={15} /> Regulatory intelligence built for SMEs <ArrowRight size={15} /></a>
          <h1>Regulations change.<br /><span>Know what it means<br className="hero-mobile-break" /> for your business.</span></h1>
          <p>Understand what changed, discover how it may affect your business, and turn complex regulatory requirements into clear, evidence-backed actions.</p>
          <div className="hero-buttons"><button className="landing-button primary" onClick={onAnalyze}>Analyze a regulation <ArrowRight size={17} /></button><a className="landing-button secondary" href="#how-it-works">See how it works <ChevronDown size={17} /></a></div>
          <ul className="trust-list"><li><Check size={16} /> Source-linked analysis</li><li><Check size={16} /> Business-specific impact</li><li><Check size={16} /> Action-oriented reports</li></ul>
        </div>
        <ProductPreview />
      </section>

      <section className="landing-section features-section" id="features">
        <div className="section-heading"><span className="section-kicker">A CLEARER WAY TO RESPOND</span><h2>From regulatory changes<br /><em>to confident action.</em></h2><p>Niyam AI helps small and medium businesses understand what changed, whether it may affect them, and what to investigate or do next.</p></div>
        <div className="feature-grid">{features.map((feature, index) => <article className="feature-card" key={feature.title} style={{ '--delay': `${index * 55}ms` } as React.CSSProperties}><div className="feature-card-top"><span className="feature-icon"><feature.icon size={21} strokeWidth={1.8} /></span><span className="feature-number">/ 0{index + 1}</span></div><h3>{feature.title}</h3><p>{feature.description}</p><div className="feature-foot"><span>{feature.note}</span><ArrowDownRight size={17} /></div></article>)}</div>
      </section>

      <section className="landing-section preview-section" id="product-preview">
        <div className="preview-intro"><span className="section-kicker">PRODUCT PREVIEW</span><h2>Evidence first.<br /><em>Action follows.</em></h2><p>A glimpse of how a team can review changes, confirm scope, and keep source evidence close at hand.</p><span className="demo-label"><span /> FICTIONAL DEMONSTRATION DATA</span></div>
        <ProductPreview large />
      </section>

      <section className="landing-section workflow-section" id="how-it-works">
        <div className="section-heading workflow-heading"><span className="section-kicker">HOW IT WORKS</span><h2>Five steps from document<br /><em>to informed next step.</em></h2><p>Every assessment is grounded in source text and the business details you provide.</p></div>
        <div className="workflow-track">{workflow.map((step, index) => <article className="workflow-step" key={step.title}><div className="workflow-step-top"><span className="workflow-icon"><step.icon size={20} /></span><span className="workflow-index">0{index + 1}</span></div><h3>{step.title}</h3><p>{step.detail}</p>{index < workflow.length - 1 && <span className="workflow-connector" aria-hidden="true"><ArrowRight size={17} /></span>}</article>)}</div>
        <div className="workflow-cta"><span>Ready to review a regulation?</span><button className="landing-button primary" onClick={onAnalyze}>Begin an analysis <ArrowRight size={16} /></button></div>
      </section>

      <section className="landing-section demo-section" id="demonstration">
        <div className="section-heading demo-heading"><span className="section-kicker">BEFORE & AFTER</span><h2>See the change.<br /><em>Understand the context.</em></h2><p>Explore a fictional example. It is product demonstration content, not legal guidance or a real regulation.</p></div>
        <div className="demo-shell">
          <div className="demo-toolbar"><div className="demo-toolbar-title"><span className="demo-live-dot" /> Example comparison <span className="fictional-pill">FICTIONAL</span></div><div className="demo-switcher" aria-label="Choose a fictional change example">{demoChanges.map((change, index) => <button className={demoIndex === index ? 'active' : ''} key={change.title} onClick={() => { setDemoIndex(index); setExpanded(true) }}>Example {index + 1}</button>)}</div></div>
          <div className="demo-content"><div className="demo-change-title"><div><span className="demo-clause-label">{currentDemo.clause}</span><h3>{currentDemo.title}</h3></div><button className="demo-expand" aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>{expanded ? 'Collapse' : 'View change'} <ChevronDown className={expanded ? 'rotated' : ''} size={16} /></button></div>
            {expanded && <><div className="demo-text-grid"><div className="demo-provision previous"><span>PREVIOUS PROVISION</span><p>{currentDemo.oldText}</p></div><div className="demo-provision updated"><span>UPDATED PROVISION</span><p>{currentDemo.newText}</p></div></div><div className="demo-result"><div className="demo-result-main"><span className="result-eyebrow"><Sparkles size={14} /> WHAT CHANGED</span><p>{currentDemo.title}: wording in the updated sample differs from the earlier sample.</p><span className="result-eyebrow"><Building2 size={14} /> WHY IT MAY MATTER</span><p>{currentDemo.impact}</p></div><div className="demo-result-side"><span className={`assessment-status ${currentDemo.applicability === 'Potentially Applicable' ? 'possible' : 'verify'}`}><CircleHelp size={14} /> {currentDemo.applicability}</span><span className="result-eyebrow">RECOMMENDED NEXT ACTION</span><p>{currentDemo.action}</p><div className="result-date"><CalendarClock size={16} /><span>{currentDemo.date}</span></div><span className="source-ref"><FileText size={14} /> {currentDemo.clause} · sample citation</span></div></div></>}
            <p className="fictional-disclaimer">Demonstration only. All provisions, dates, status labels, and recommendations in this panel are fictional examples and are not real legal requirements.</p>
          </div>
        </div>
      </section>

      <section className="impact-section" id="business-impact">
        <div className="impact-inner"><div className="impact-copy"><span className="section-kicker">BUSINESS-SPECIFIC ASSESSMENT</span><h2>Your business context<br />changes the <em>answer.</em></h2><p>Potential applicability is assessed against the profile details you provide, such as industry, jurisdiction, employee count, and business activities. Missing facts remain visible for follow-up.</p><small>Niyam AI supports decision-making; it does not guarantee legal accuracy or compliance.</small></div><div className="assessment-list"><AssessmentStatus status="applicable" title="Applicable" detail="Available evidence indicates the requirement may apply." /><AssessmentStatus status="excluded" title="Not Applicable" detail="Available evidence indicates the requirement may not apply." /><AssessmentStatus status="verify" title="Needs Verification" detail="Information is missing or the wording requires human review." /></div></div>
      </section>

      <section className="final-cta"><div className="final-cta-inner"><span className="section-kicker">NIYAM AI · REGULATORY INTELLIGENCE</span><h2>Turn regulatory uncertainty<br /><em>into your next clear action.</em></h2><p>Understand regulatory changes, evaluate potential business impact, and know what to investigate or do next.</p><button className="landing-button primary" onClick={onAnalyze}>Start analyzing <ArrowRight size={17} /></button><span className="cta-footnote"><Shield size={14} /> Evidence-led decision support for SMEs</span></div></section>
    </main>

    <footer className="landing-footer"><div className="footer-main"><div className="footer-brand-col"><Logo /><p>Regulatory intelligence that helps SMEs understand change and decide what to do next.</p><span className="footer-disclaimer">AI-generated insights support decision-making and do not replace official legal guidance.</span></div><div className="footer-links"><div><span>EXPLORE</span><a href="#features">Features</a><a href="#how-it-works">How it works</a><a href="#product-preview">Product preview</a><a href="#demonstration">Example analysis</a></div><div><span>WORKSPACE</span><button onClick={onAnalyze}>Analyze a regulation</button><button onClick={() => showAuthPlaceholder('Sign in')}>Sign in</button><button onClick={() => showAuthPlaceholder('Admin login')}>Admin login</button></div></div></div><div className="footer-bottom"><span>© {new Date().getFullYear()} Niyam AI</span><span>Decision support, not legal advice</span></div></footer>

    {authMessage && <div className="landing-dialog-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) setAuthMessage('') }}><section className="landing-dialog" role="alertdialog" aria-modal="true" aria-labelledby="auth-placeholder-title"><button className="dialog-close" aria-label="Close" onClick={() => setAuthMessage('')}><X size={18} /></button><span className="dialog-shield"><ShieldCheck size={23} /></span><h2 id="auth-placeholder-title">Authentication setup needed</h2><p>{authMessage}</p><div><button className="landing-button secondary" onClick={() => setAuthMessage('')}>Close</button><button className="landing-button primary" onClick={() => { setAuthMessage(''); onAnalyze() }}>Explore analysis <ArrowRight size={16} /></button></div></section></div>}
  </div>
}

function ProductPreview({ large = false }: { large?: boolean }) {
  const [activeTab, setActiveTab] = useState<'changes' | 'evidence'>('changes')
  return <div className={`product-preview ${large ? 'product-preview-large' : ''}`} aria-label="Fictional Niyam AI product dashboard preview">
    <div className="mock-window-bar"><div className="mock-window-dots"><i /><i /><i /></div><span>NIYAM AI WORKSPACE</span><span className="mock-window-profile">NS</span></div>
    <div className="mock-app"><aside className="mock-sidebar"><div className="mock-side-brand"><span><ShieldCheck size={14} /></span><b>Niyam</b></div><div className="mock-side-label">WORKSPACE</div><div className="mock-side-item"><span className="mock-nav-icon"><Bell size={13} /></span>Overview</div><div className="mock-side-item active"><span className="mock-nav-icon"><GitCompareArrows size={13} /></span>Changes <b>4</b></div><div className="mock-side-item"><span className="mock-nav-icon"><ClipboardCheck size={13} /></span>Actions</div><div className="mock-side-profile"><span className="mock-avatar">NS</span><div><b>Northstar Studio</b><small>Business profile</small></div></div></aside>
      <div className="mock-main"><div className="mock-topline"><div><small>MONDAY, 25 OCTOBER 2026</small><h3>Regulatory overview</h3></div><span className="mock-source-state"><i /> Monitoring active</span></div><div className="mock-metrics"><div><small>Updates to review</small><b>04</b><span>Across 3 sources</span></div><div><small>Potentially applicable</small><b>02</b><span>Profile-matched</span></div><div><small>Upcoming dates</small><b>02</b><span>Source-verified</span></div></div><div className="mock-update-row"><span className="mock-update-icon"><FileText size={14} /></span><div><b>Illustrative packaging notification</b><small>Example update · 2 provisions changed</small></div><span className="mock-status needs">Review</span></div><div className="mock-analysis"><div className="mock-analysis-head"><div><small>BEFORE VS. AFTER</small><b>Employee threshold</b></div><div className="mock-tabs"><button className={activeTab === 'changes' ? 'selected' : ''} onClick={() => setActiveTab('changes')}>Changes</button><button className={activeTab === 'evidence' ? 'selected' : ''} onClick={() => setActiveTab('evidence')}>Evidence</button></div></div>{activeTab === 'changes' ? <div className="mock-compare"><span className="old">100 employees</span><ArrowRight size={14} /><span className="new">50 employees</span><span className="mock-status verify">Needs verification</span></div> : <div className="mock-evidence"><FileSearch size={14} /><span>Illustrative Clause 7 · page 5</span><b>Source excerpt linked</b></div>}</div><div className="mock-action"><span className="mock-action-check"><Check size={13} /></span><div><b>Confirm employee count and scope</b><small>Suggested next step · verify source wording</small></div><span className="mock-action-date">Review</span></div></div></div>
    <div className="mock-window-caption"><Sparkles size={13} /> Product interface preview <span>All dashboard details shown are fictional sample data</span></div>
  </div>
}

function AssessmentStatus({ status, title, detail }: { status: 'applicable' | 'excluded' | 'verify'; title: string; detail: string }) {
  const Icon = status === 'applicable' ? CheckCircle2 : status === 'excluded' ? ShieldCheck : CircleHelp
  return <article className={`assessment-row ${status}`}><span className="assessment-icon"><Icon size={19} /></span><div><h3>{title}</h3><p>{detail}</p></div><ArrowRight className="assessment-arrow" size={16} /></article>
}
