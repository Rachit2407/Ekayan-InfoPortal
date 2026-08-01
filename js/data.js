// js/data.js
// Supabase Integration & LocalStorage fallback

const mockData = [
  {
    id: "opp-1",
    category: "admissions",
    title: "B.Tech Admissions 2026",
    organization: "Delhi Technological University",
    deadline: "2026-08-15",
    description: "Open admissions for incoming undergraduate engineering students. Must have completed Class 12 with PCM.",
    link: "https://example.com/dtu-admissions",
    status: "approved"
  },
  {
    id: "opp-2",
    category: "scholarships",
    title: "Ekayan Merit Scholarship",
    organization: "Ekayan Foundation",
    deadline: "2026-07-30",
    description: "Financial assistance up to ₹50,000 for deserving students from underprivileged backgrounds.",
    link: "https://example.com/ekayan-scholarship",
    status: "approved"
  },
  {
    id: "opp-3",
    category: "fellowships",
    title: "Teach For India Fellowship",
    organization: "Teach For India",
    deadline: "2026-09-01",
    description: "A 2-year full-time paid commitment to teach in under-resourced schools.",
    link: "https://example.com/tfi",
    status: "approved"
  },
  {
    id: "opp-4",
    category: "jobs",
    title: "Junior Frontend Developer",
    organization: "TechCorp India",
    deadline: "2026-07-20",
    description: "Looking for fresh graduates with HTML/CSS/JS knowledge. Remote work available.",
    link: "https://example.com/job1",
    status: "approved"
  }
];

// Initialize local storage if empty
if (!localStorage.getItem('ekayan_opportunities')) {
  localStorage.setItem('ekayan_opportunities', JSON.stringify(mockData));
}

// Helper: Get raw localStorage array
function getLocalOpps() {
  return JSON.parse(localStorage.getItem('ekayan_opportunities') || '[]');
}

// Helper: Save raw localStorage array
function saveLocalOpps(data) {
  localStorage.setItem('ekayan_opportunities', JSON.stringify(data));
}

// ─────────────────────────────────────────────
// Public / Approved opportunities (For portal.html & admin.html manage table)
// ─────────────────────────────────────────────
window.getOpportunities = async function() {
  if (window.supabaseClient) {
    try {
      const { data, error } = await window.supabaseClient
        .from('opportunities')
        .select('*')
        .eq('status', 'approved');
      if (!error && data) return data;
      console.warn("Supabase query error, falling back to LocalStorage:", error);
    } catch (e) {
      console.warn("Supabase connection failed, falling back to LocalStorage:", e);
    }
  }
  return getLocalOpps().filter(o => o.status === 'approved' || !o.status);
};

// ─────────────────────────────────────────────
// Upsert (Insert or Update) opportunity
// ─────────────────────────────────────────────
window.upsertOpportunity = async function(opp) {
  if (window.supabaseClient) {
    try {
      const { error } = await window.supabaseClient
        .from('opportunities')
        .upsert(opp);
      if (!error) return;
      console.warn("Supabase upsert error, falling back to LocalStorage:", error);
    } catch (e) {
      console.warn("Supabase connection failed, falling back to LocalStorage:", e);
    }
  }
  
  let local = getLocalOpps();
  const idx = local.findIndex(o => o.id === opp.id);
  if (idx !== -1) {
    local[idx] = opp;
  } else {
    local.push(opp);
  }
  saveLocalOpps(local);
};

// ─────────────────────────────────────────────
// Delete opportunity
// ─────────────────────────────────────────────
window.deleteOpportunity = async function(id) {
  if (window.supabaseClient) {
    try {
      const { error } = await window.supabaseClient
        .from('opportunities')
        .delete()
        .eq('id', id);
      if (!error) return;
      console.warn("Supabase delete error, falling back to LocalStorage:", error);
    } catch (e) {
      console.warn("Supabase connection failed, falling back to LocalStorage:", e);
    }
  }
  
  let local = getLocalOpps();
  local = local.filter(o => o.id !== id);
  saveLocalOpps(local);
};

// ─────────────────────────────────────────────
// Legacy compatibility wrappers (to prevent breaking any old code)
// ─────────────────────────────────────────────
window.saveOpportunities = function(data) {
  saveLocalOpps(data);
};
