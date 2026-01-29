# The TV Signal - Technical Specification

## Project Overview

The TV Signal is an agentic workflow system that uses Antigravity (manager) and Claude Code CLI (workers) to automatically extract Reddit's /r/television RSS feed daily at 11 PM EST, filter for high-engagement discussion threads, and generate a mobile-responsive HTML digest delivered in under 5 minutes.

**Core Value Proposition:** Stay current on TV discussions without opening Reddit - save time (3 min digest vs 15 min scrolling) through signal extraction (42 curated discussions vs 200 mixed posts with trailers/noise) with comment insights surfaced.

**Primary Competition:** Reddit.com itself (users scrolling the subreddit daily), not other automation tools.

---

## Technical Architecture

### System Design

**7-Task Pipeline (Serial Execution):**
1. Fetch RSS feed from /r/television
2. Parse feed into structured data
3. Deduplicate against 200 seen IDs
4. Filter for high-engagement content
5. Extract top comments (with graceful degradation)
6. Render mobile-responsive HTML digest
7. Update project memory in CLAUDE.md

**Orchestration:** Fully serial waterfall execution for learning project simplicity. Each task completes before the next starts.

### Technology Stack

**Core Language:** Python for all 7 tasks
- `feedparser` - RSS parsing
- `requests` - Reddit API calls
- `jinja2` - HTML templating
- Standard library for file I/O

**Rationale:** Single-language stack avoids context-switching, simplifies debugging (one stack trace format), leverages mature libraries. No Bash scripts, no JavaScript mixing.

**Fallback Strategy:** If Antigravity + Claude Code proves unreliable:
1. **Primary fallback:** 50-line `run_digest.sh` calling 7 Python scripts sequentially with error handling
2. **Secondary fallback:** Single 500-line Python script (fetch→filter→render) if orchestration is over-engineered

### Infrastructure

**Hosting:** VPS (DigitalOcean/Linode) at $5-10/month
- Provides full OS access and control for learning
- Dedicated VM for reliable 24/7 operation
- No timeout limits unlike GitHub Actions

**Reliability Requirements:**
- Daily health checks with automated restart on crash
- CLAUDE.md backed up to GitHub every 6 hours via cron job
- **Non-negotiable:** Infrastructure reliability - losing user data or 48-hour downtime kills trust permanently

### Data Integration

**Reddit API Strategy:** Reddit API as primary with RSS fallback
- Use official Reddit API for richer data (comment threads, vote counts)
- Implement RSS feed parsing as graceful degradation when rate limits hit
- Provides resilience against API changes while accessing full comment data

**Comment Extraction:** Direct API calls without MCP
- Call Reddit API directly from agents (skip MCP abstraction)
- Simpler architecture for MVP
- Loses MCP benefits (caching, reusability) but faster to implement

**Legal Compliance:** Public RSS parsing only
- Only use publicly available RSS feeds without authentication
- Argue no ToS violation for public data
- **Legal review triggered at $500 MRR** before scaling paid tiers

---

## Content Curation

### Filtering Logic

**Multi-layer approach to exclude promotional noise:**

1. **Flair Allowlist:**
   - Whitelist approved flairs: "Discussion", "Review", "Episode Discussion"
   - Blacklist promotional flairs: "Trailer", "Casting", "News", "Premiere Date"
   - Relies on /r/television moderators tagging correctly

2. **Title Keyword Filtering:**
   - Exclude posts containing: "trailer", "cast", "renewed", "cancelled", "streaming on"
   - Catches unflaired promotional content

3. **Engagement Ratio Threshold:**
   - Filter posts with high upvotes but low comments (comment-to-score ratio)
   - Promotional posts get upvotes but generate less discussion

**Minimum Engagement:** >50 comments per thread

### Quality Assurance

**Manual Review Phase (First 30 days):**
- Read every digest personally
- Note false positives (e.g., threads that are just price arguments despite passing filters)
- Tighten keyword exclusions and add edge cases based on real failures
- Tune filters based on personal judgment of quality

**Engagement-Based Feedback (After 50 Tier 2 users):**
- Track click-through rates per post position
- If 80% of clicks are top 10 posts and bottom 20 get <5% clicks, adjust filters
- Let usage data reveal what "interesting" means to users
- Refine comment thresholds or flair weights based on click patterns

---

## User Experience

### HTML Digest Design

**Format:** Minimal static HTML with inline CSS
- Plain semantic HTML with embedded styles
- No JavaScript
- Optimized for fast generation and universal email client compatibility
- Mobile-responsive layout

**Performance Target:** 5-minute generation time (revised from 3 minutes)
- Pragmatic acceptance that 3 minutes may be too aggressive for quality output
- **Safety valve:** Reduce comment extraction depth (fewer top comments per thread) if time budget exceeded

### Error Handling & Graceful Degradation

**When Reddit API Fails:**
- **Notification of degraded mode** - Generate digest with clear notice that comments are unavailable and when normal service will resume
- Sets user expectations vs delivering partial/stale data
- Maintains transparency about system status

**When RSS Feed Format Changes:**
- **Hybrid approach:**
  1. Detect parsing failure, serve yesterday's cached digest with notice
  2. Open-source repo allows community to submit parser fixes via PR
  - Maintains uptime while crowdsourcing resilience

**Comprehensive Error Handling:**
- System produces fallback digests when critical tasks fail
- Users always receive a file (never silent failures)
- Graceful degradation ensures core value delivery even with partial failures

---

## State Management

### Deduplication System

**Implementation:** Fixed 200-ID rolling window
- Store 200 most recent post IDs in memory/simple file
- Simple and fast implementation
- Trade-off: May re-show old content after ~7 days of high activity
- Sufficient for MVP and daily digest cadence

### Project Memory (CLAUDE.md)

**Tracked Information:**
1. **200 deduplicated post IDs** - Rolling window of seen thread IDs
2. **Workflow execution metrics** - Run times, success/failure rates, API errors for debugging

**Update Frequency:** Every workflow run updates CLAUDE.md
**Backup Strategy:** Git push every 6 hours to prevent data loss

---

## Observability & Monitoring

**Comprehensive monitoring stack (all complementary):**

1. **Structured Logging:**
   - Each agent task writes detailed logs with timestamps, inputs, outputs
   - Logs stored to files on VPS for post-failure inspection

2. **Status Dashboard:**
   - Simple web dashboard showing last run time, task success/failure, key metrics
   - Quick visual health check

3. **Alert Notifications:**
   - Email/Discord alerts when workflow fails or exceeds 5-minute target
   - Enables investigation before users notice issues

4. **Task Artifacts:**
   - Persist intermediate outputs (filtered JSON, raw API responses) for each run
   - Enables debugging of transform logic without re-running entire pipeline

---

## Business Model

### Revenue Target

**$900 MRR within 6 months**

**Customer Mix:**
- 50 Tier 2 customers at $9/month = $450
- 10 Tier 3 customers at $49/month = $490
- Total: $940 MRR

**Diversified revenue** across individual enthusiasts (Tier 2) and B2B customers (Tier 3).

### Tier Structure

#### Tier 1: Free Self-Hosting (Open Source)
- Complete codebase available on GitHub
- Users run workflow on their own infrastructure
- Generate HTML digests locally
- **Target:** GitHub stars, community contribution, distribution

#### Tier 2: Managed Email Delivery ($9/month)
- Daily digest delivered via email at 11 PM EST
- No infrastructure setup required
- Mobile-responsive HTML email format
- **Value prop:** "Just works" convenience vs running cron jobs

#### Tier 3: B2B API Access ($49/month)
- **Historical data access:** Query past digests and archived threads (weeks/months back)
- **Structured JSON endpoints:** Programmatic access to parsed thread data, comments, metadata
- Integration with customer tools/dashboards
- **Target:** Media companies, entertainment journalists, TV critics

### Email Delivery Infrastructure

**Service:** Budget ESP (Brevo/Postmark free tier)
- Start with free tiers (300-1000 emails/day)
- Good deliverability without cutting into margin
- Upgrade as customer base scales
- Purpose-built for transactional email with analytics

**Deliverability:** SPF/DKIM/DMARC configuration handled by ESP

### Authentication Strategy

**Dual approach by tier:**

1. **Tier 1 & 2:** Email-only magic links
   - Passwordless authentication via emailed tokens
   - Simple UX, no password storage
   - Low friction for consumer signups

2. **Tier 3:** API keys
   - Programmatic authentication for B2B customers
   - Keys provided manually via email for early customers
   - Self-serve API key generation post-MVP

**Payment Processing:** Stripe integration (deferred to post-MVP validation)

---

## Development Strategy

### MVP Scope & Timeline

**Phase 1 (Weeks 1-4): Core Workflow Only**
- Build 7-task pipeline (fetch → parse → dedupe → filter → comments → render → memory)
- Tier 1 free self-hosting functionality
- No authentication, no email delivery, no API
- **Deliverable:** Open-source repo with working digest generator

**Validation Checkpoint (End of Week 4):**
- Assess GitHub stars, community engagement, user feedback
- Look for signals: 100+ stars, 20+ "I'd pay for email" comments
- **Decision:** Proceed to Tier 2 if validation is strong

**Phase 2 (Weeks 5-6): Tier 2 Email Delivery** *(conditional)*
- Add email-only magic link authentication
- Integrate Brevo/Postmark for email delivery
- Stripe payment integration
- Self-serve signup flow

**Phase 3 (Post-Launch): Tier 3 B2B API** *(deferred)*
- Build after Tier 2 proves revenue model
- Historical data access endpoints
- API key management system
- JSON response schemas

### Time Budget

**Total Development Budget:** 80 hours
- Kill criteria triggered if development exceeds this without revenue

**Biggest Risk:** Antigravity learning curve
- First time using Antigravity + Claude Code in production
- Unknown unknowns in workflow orchestration
- Mitigate through iterative refinement approach (see below)

### Task Definition Methodology

**Iterative Refinement Approach:**
1. Start with simple imperative instructions for each task
   - Example: "fetch RSS from X, save to /home/claude/raw_feed.xml, validate with xmllint"
2. Run full pipeline manually 3-5 times in development
3. Observe where workers fail or produce unexpected outputs
4. Tighten prompts and add acceptance tests based on actual failure modes

**Rationale:** Writing perfect JSON schemas upfront wastes hours guessing worker behavior. Better to write "fetch → parse → filter" in plain English, let Claude Code execute it, then add structure only where ambiguity caused real problems.

### Acceptable Technical Debt

**Embrace for MVP:**

1. **No automated tests** - Skip unit/integration tests for v1
   - Rely on manual testing and monitoring
   - Low-stakes for side project, bugs are tolerable
   - Manually test each run and monitor logs

2. **Hardcoded configuration** - Bake values into Python scripts
   - `MIN_COMMENTS=50`, `SUBREDDIT="television"` directly in code
   - Takes 2 minutes to change vs 4 hours building config system
   - Sufficient until serving multiple configurations

3. **Manual user onboarding** - No self-serve signup initially
   - For first 10-20 Tier 2 customers, provision accounts manually via email
   - Send credentials personally, validate they're real humans
   - Gather direct feedback during onboarding
   - "Unscalable" approach teaches what users need before automating

**Never Compromise:**
- Infrastructure reliability (see Infrastructure section)
- Data backup and persistence
- User data security

---

## Go-to-Market Strategy

### Launch Distribution (Multi-Channel)

1. **Post to /r/television and media subreddits**
   - Direct outreach to target audience where they already congregate
   - High relevance but risk of self-promotion backlash
   - Position as "I built this for myself" story

2. **Product Hunt / Hacker News launch**
   - Reach tech-savvy early adopters who appreciate agentic workflows
   - Good for GitHub stars and technical feedback
   - Emphasize the Antigravity + Claude Code architecture as novel

3. **Developer community content**
   - Write technical blog post about Antigravity + Claude Code architecture
   - Position as case study of agentic workflows in production
   - Attracts other builders, drives GitHub engagement

### Success Metrics

**Track retention over vanity metrics:**

1. **90-day retention:** 60%+ of Tier 2 subscribers still paying after 90 days
   - Proves daily habit formation
   - More important than initial conversion rate

2. **Usage frequency:** Free Tier 1 users run digest script 5+ times per week
   - Check GitHub clone activity and self-reported usage
   - Indicates integration into daily routine

3. **Organic social sharing:** Users posting "found this via The TV Signal" without prompting
   - Word-of-mouth growth signal
   - Proves genuine value delivery

4. **API customer engagement:** Tier 3 customers making 500+ API calls/month
   - Not just trying it once
   - Indicates integration into actual workflow

**Email engagement benchmarks:**
- Daily digest open rates >40% (industry standard is 20-30%)
- Consistent opens mean users find ongoing value

### Kill Criteria & Contingency

**Original Criteria:**
- <50 GitHub stars after 30 days
- Development exceeds 80 hours without revenue

**Contingency Plan: Revenue trumps vanity metrics**

**Scenario:** 10+ paying Tier 2 customers ($90 MRR) with 70%+ open rates after 30 days, but only 35 GitHub stars

**Response:**
1. **Recognize kill criteria was wrong** - Built something people pay for
2. **Post-mortem analysis:**
   - Why are stars low? (Wrong launch timing on HN? Didn't cross-post to /r/cordcutters? README not compelling?)
3. **Relaunch with better positioning** while keeping paying customers happy
4. Consider pivot to B2B-only if GitHub traction remains weak but revenue is strong

**Core principle:** The goal is learning what works, not blindly following arbitrary thresholds when real revenue signals say "people want this."

---

## Vertical Expansion Strategy

### Timing

**Primary Focus:** TV content for /r/television until proven
- Validate technology and hit $900 MRR target first
- Only explore other verticals if TV fails kill criteria at 30/90 days
- OR after proving tech with TV (6+ months), clone for profitable verticals

### Target Verticals (Future)

**High-value monitoring opportunities:**
- Legal: /r/law, /r/lawyers - case law discussions, regulation changes
- Finance: /r/investing, /r/wallstreetbets - market sentiment, DD posts
- Real Estate: /r/realestate, /r/realestateinvesting - market trends, deals

**Template Approach:** System designed to be vertically-agnostic
- Same architecture, different subreddit and filter criteria
- Each vertical becomes separate product/offering
- Leverage learning from TV Signal as replicable template

---

## Open Source Strategy

### Licensing

**Fully open source from day one**
- All code public including email delivery and API implementation
- MIT or similar permissive license
- Accept that others can clone and self-host

### Competitive Moat

**Not the code - the distribution and convenience:**

1. **Hosted convenience:** Email delivery that "just works"
   - 95% of users will pay $9/month to avoid running cron jobs
   - Self-hosting requires VPS, maintenance, monitoring

2. **Network effects:** 50+ users trusting your curated output
   - Reputation for quality and reliability
   - First-mover advantage in the niche

3. **Distribution:** Being the first/default option people find
   - GitHub stars, HN visibility, SEO for "TV discussion digest"
   - Community momentum

**Trade-off:** Users who clone to run privately were never going to pay anyway. Every fork/star increases visibility and GitHub traction, which is primary customer acquisition channel.

**Benefit:** Open source unlocks HN credibility, contributor energy, and transparent roadmap via GitHub Issues.

---

## Feedback & Iteration

### Feedback Collection *(Post-MVP)*

**Channels selected:** *(Note: User didn't provide answer, needs follow-up)*

Options considered:
- Feedback form in digest footer (Google Form/Typeform)
- GitHub Issues for feature requests (transparent roadmap)
- User interviews via email outreach (5+ digest opens)
- Usage analytics (open rates, clicks)

### Feature Prioritization

**User-driven roadmap:**
- GitHub Issues with community voting on features
- Proactive outreach to engaged users (opened 5+ digests)
- 15-minute calls to understand their workflow
- Track which digest sections get clicked to optimize content mix

---

## Risk Mitigation

### Technical Risks

1. **Antigravity/Claude Code production readiness**
   - **Risk:** Bleeding-edge tooling hits unknown issues
   - **Mitigation:** Fallback to Bash orchestrator or single Python script
   - **Decision point:** After 3-5 manual dev runs

2. **Reddit API/ToS changes**
   - **Risk:** Reddit changes RSS access, rate limits, or sends C&D
   - **Mitigation:** RSS fallback, public data only, legal review at $500 MRR
   - **Monitoring:** Alert on parsing failures, track API response codes

### Product Risks

1. **Product-market fit**
   - **Risk:** Not enough people want daily TV discussion digests
   - **Mitigation:** 30-day validation checkpoint, kill criteria
   - **Early signals:** GitHub stars, "I'd pay for this" comments, clone activity

2. **Time commitment exceeding budget**
   - **Risk:** Scope creep or learning curve pushes past 80 hours
   - **Mitigation:** Strict MVP scope, acceptable technical debt, time tracking
   - **Checkpoint:** Weekly hour logging, kill at 80 hours without revenue

### Business Risks

1. **Email deliverability**
   - **Risk:** Daily digests land in spam folder
   - **Mitigation:** Budget ESP with good reputation, SPF/DKIM/DMARC
   - **Monitoring:** Track open rates, bounce rates

2. **VPS reliability**
   - **Risk:** Single point of failure, no redundancy
   - **Mitigation:** Daily health checks, automated restart, GitHub backup
   - **Acceptable:** Downtime of hours (not days), no data loss

---

## Vision & Success Criteria

### 3-Month Success Vision *(Post-MVP)*

**Definition of success:** *(Note: User didn't provide answer, needs follow-up)*

Options considered:
- Power user of own product (daily routine, would miss if broken)
- Strong customer engagement despite personal non-use (product-market fit without dogfooding)
- Autonomous operation (runs reliably without manual intervention)
- Vertical expansion (TV + 2 other subreddits/verticals)

### Remaining Technical Uncertainties

**Areas needing clarification:** *(Note: User didn't provide answer, needs follow-up)*

Potential gaps:
- Reddit API authentication flow (OAuth/API keys setup)
- CLAUDE.md state management schema (data structure, safe read/write)
- HTML email rendering cross-client (Gmail vs Outlook vs Apple Mail testing)
- Antigravity task dependency definition (expressing dependencies in config/API)

---

## Document Status

**Last Updated:** 2026-01-27

**Next Steps:**
1. Clarify remaining uncertainties (vision, feedback channels, technical gaps)
2. Begin Phase 1 development: 7-task pipeline implementation
3. Manual testing with 3-5 dev runs to validate Antigravity approach
4. Launch Tier 1 open source at end of Week 4

**Decision Log:**
- All architectural and strategic decisions documented above based on detailed interview
- Technical debt boundaries clearly defined (accept vs never compromise)
- Kill criteria and contingency plans established
- Fallback strategies defined for all major risks
