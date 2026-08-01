// js/review.js
// Admin Approval Queue Controller supporting Supabase + LocalStorage fallback

// Page routing switcher
window.switchAdminTab = function(tab) {
  document.getElementById('section-manage').style.display = tab === 'manage' ? '' : 'none';
  document.getElementById('section-review').style.display = tab === 'review' ? '' : 'none';
  document.getElementById('tab-manage').classList.toggle('active', tab === 'manage');
  document.getElementById('tab-review').classList.toggle('active', tab === 'review');
};

// ─────────────────────────────────────────────
// Pending data helpers
// ─────────────────────────────────────────────
async function getPending() {
  if (window.supabaseClient) {
    try {
      const { data, error } = await window.supabaseClient
        .from('opportunities')
        .select('*')
        .eq('status', 'pending');
      if (!error && data) return data;
      console.warn("Supabase pending fetch failed, falling back to LocalStorage:", error);
    } catch (e) {
      console.warn("Supabase pending fetch connection failed:", e);
    }
  }
  return JSON.parse(localStorage.getItem('ekayan_pending') || '[]');
}

function savePendingLocal(data) {
  localStorage.setItem('ekayan_pending', JSON.stringify(data));
}

function updateBadge(count) {
  document.getElementById('pending-badge').textContent = count;
}

// ─────────────────────────────────────────────
// Render Review Queue
// ─────────────────────────────────────────────
async function renderReviewQueue() {
  const container = document.getElementById('review-queue-container');
  let items = [];
  try {
    items = await getPending();
  } catch (e) {
    console.error("Error reading pending queue:", e);
  }
  
  // Filter for local storage items that are pending
  if (!window.supabaseClient) {
    items = items.filter(i => i.status === 'pending');
  }
  updateBadge(items.length);

  if (items.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <p style="font-size:1.1rem;">✅ No items pending review.</p>
        <p style="margin-top:0.5rem; font-size:0.85rem;">
          Run <code style="background:rgba(255,255,255,0.1);padding:2px 6px;border-radius:4px;">python scraper.py</code> after adding source URLs to fetch new opportunities.
        </p>
      </div>`;
    return;
  }

  container.innerHTML = '';

  items.forEach(item => {
    const card = document.createElement('div');
    card.className = 'card';
    card.style.marginBottom = '1rem';

    const deadline = item.deadline
      ? new Date(item.deadline).toLocaleDateString('en-GB')
      : 'Not specified';

    card.innerHTML = `
      <div class="card-header">
        <span class="card-category">${item.category || 'unknown'}</span>
        <span class="card-deadline">📅 ${deadline}</span>
      </div>
      <h3 class="card-title" style="margin-bottom:0.3rem;">${item.title}</h3>
      <div class="card-org">${item.organization || 'Unknown org'}</div>
      <p class="card-desc">${item.description}</p>
      <div style="font-size:0.8rem; color:var(--text-muted); margin-bottom:1rem;">
        🔗 Source: <a href="${item.source_url}" target="_blank" style="color:var(--primary-color);">${item.source_url}</a>
        &nbsp;|&nbsp; Found on: ${item.ai_found_on}
      </div>
      <div class="card-footer" style="gap:10px;">
        <button class="btn btn-primary btn-approve" data-id="${item.id}" style="flex:1;">✅ Approve — Publish Live</button>
        <button class="btn btn-danger btn-reject" data-id="${item.id}" style="flex:1;">❌ Reject</button>
      </div>
    `;

    container.appendChild(card);
  });

  // Attach approve/reject handlers
  document.querySelectorAll('.btn-approve').forEach(btn => {
    btn.addEventListener('click', (e) => handleApprove(e.target.closest('button').dataset.id));
  });
  document.querySelectorAll('.btn-reject').forEach(btn => {
    btn.addEventListener('click', (e) => handleReject(e.target.closest('button').dataset.id));
  });
}

// ─────────────────────────────────────────────
// Helper to resolve the best link, avoiding generic root homepages
function getEffectiveLink(link, source) {
  if (!link) return source || '';
  try {
    const u = new URL(link.trim());
    if ((u.pathname === '/' || u.pathname === '') && !u.search && source) {
      return source.trim();
    }
  } catch (e) {}
  return link.trim();
}

// Approve: move from pending → live opportunities
// ─────────────────────────────────────────────
async function handleApprove(id) {
  let item = null;
  
  if (window.supabaseClient) {
    try {
      // Retrieve the pending item first to resolve its link
      const { data: findData, error: findError } = await window.supabaseClient
        .from('opportunities')
        .select('*')
        .eq('id', id);
        
      if (!findError && findData && findData.length > 0) {
        const tempItem = findData[0];
        const resolvedLink = getEffectiveLink(tempItem.link, tempItem.source_url);
        
        const { data, error } = await window.supabaseClient
          .from('opportunities')
          .update({ 
            status: 'approved',
            link: resolvedLink
          })
          .eq('id', id)
          .select();
          
        if (!error && data && data.length > 0) {
          item = data[0];
        }
      }
      if (findError) {
        console.warn("Supabase approval failed, trying LocalStorage fallback:", findError);
      }
    } catch (e) {
      console.warn("Supabase approval failed:", e);
    }
  }
  
  if (!item) {
    // LocalStorage fallback
    let pending = JSON.parse(localStorage.getItem('ekayan_pending') || '[]');
    const idx = pending.findIndex(i => i.id === id);
    if (idx !== -1) {
      pending[idx].status = 'approved';
      item = pending[idx];
      savePendingLocal(pending);
      
      // Save to live list
      let live = JSON.parse(localStorage.getItem('ekayan_opportunities') || '[]');
      live.push({
        id: item.id,
        category: item.category,
        title: item.title,
        organization: item.organization,
        deadline: item.deadline,
        description: item.description,
        link: getEffectiveLink(item.link, item.source_url)
      });
      localStorage.setItem('ekayan_opportunities', JSON.stringify(live));
    }
  }

  await renderReviewQueue();
  if (typeof renderTable === 'function') await renderTable();

  if (item) {
    // Also notify the server so it can trigger WhatsApp notification
    try {
      const res = await fetch('/approve-opportunity', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: item.id })
      });
      const data = await res.json();
      if (data.whatsapp_sent) {
        alert(`✅ "${item.title}" is now live!\n\n📲 WhatsApp notification sent to the group!`);
      } else {
        alert(`✅ "${item.title}" is now live on the public portal!\n\n(WhatsApp notifications not yet configured)`);
      }
    } catch (err) {
      // Server not running — that's fine, just show the basic alert
      alert(`✅ "${item.title}" is now live on the public portal!`);
    }
  }
}

// ─────────────────────────────────────────────
// Reject: mark as rejected (stays hidden)
// ─────────────────────────────────────────────
async function handleReject(id) {
  if (!confirm('Reject this opportunity? It will be removed from the queue.')) return;
  
  if (window.supabaseClient) {
    try {
      const { error } = await window.supabaseClient
        .from('opportunities')
        .update({ status: 'rejected' })
        .eq('id', id);
      if (!error) {
        await renderReviewQueue();
        return;
      }
      console.warn("Supabase reject failed, falling back to LocalStorage:", error);
    } catch (e) {
      console.warn("Supabase reject failed:", e);
    }
  }
  
  // Local fallback
  let pending = JSON.parse(localStorage.getItem('ekayan_pending') || '[]');
  const idx = pending.findIndex(i => i.id === id);
  if (idx !== -1) {
    pending[idx].status = 'rejected';
    savePendingLocal(pending);
  }
  await renderReviewQueue();
}

// ─────────────────────────────────────────────
// Auto-sync with pending.json
// ─────────────────────────────────────────────
async function syncPendingWithFile() {
  try {
    const res = await fetch('./pending.json');
    if (!res.ok) return;
    const fileItems = await res.json();
    if (!Array.isArray(fileItems)) return;

    if (window.supabaseClient) {
      for (const item of fileItems) {
        if (!item.status) item.status = 'pending';
        
        const { data, error } = await window.supabaseClient
          .from('opportunities')
          .select('id')
          .eq('id', item.id);
          
        if (!error && (!data || data.length === 0)) {
          await window.supabaseClient
            .from('opportunities')
            .insert(item);
        }
      }
    } else {
      // Local fallback
      let pending = JSON.parse(localStorage.getItem('ekayan_pending') || '[]');
      let updated = false;
      fileItems.forEach(fileItem => {
        if (!pending.some(i => i.id === fileItem.id)) {
          if (!fileItem.status) fileItem.status = 'pending';
          pending.push(fileItem);
          updated = true;
        }
      });
      if (updated) {
        savePendingLocal(pending);
      }
    }
  } catch (e) {
    console.log('Skipping auto-sync from pending.json (running on file:// protocol or CORS restriction).');
  }
}

// Initial render
document.addEventListener('DOMContentLoaded', async () => {
  await syncPendingWithFile();
  renderReviewQueue();
  
  // Attach run-scraper listener
  const btn = document.getElementById('btn-run-scraper');
  if (btn) {
    btn.addEventListener('click', async () => {
      const originalText = btn.textContent;
      btn.disabled = true;
      btn.textContent = '⏳ Running Scraper...';
      
      try {
        const res = await fetch('/run-scraper', {
          method: 'POST'
        });
        const data = await res.json();
        
        if (res.ok && data.success) {
          alert('🎉 Scraper completed successfully! Reloading queue...');
          await syncPendingWithFile();
          renderReviewQueue();
        } else {
          console.error('Scraper failed:', data);
          alert('⚠ Scraper run failed:\n' + (data.stderr || data.error || 'Check dev server terminal logs.'));
        }
      } catch (err) {
        console.error('Network error triggering scraper:', err);
        alert('⚠ Could not connect to dev server.\nMake sure you started "python server.py" in your terminal instead of a standard browser file view.');
      } finally {
        btn.disabled = false;
        btn.textContent = originalText;
      }
    });
  }
});
