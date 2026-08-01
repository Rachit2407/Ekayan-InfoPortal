document.addEventListener('DOMContentLoaded', () => {
  const grid = document.getElementById('opportunities-grid');
  const searchInput = document.getElementById('search-input');
  const tabs = document.querySelectorAll('.tab-btn');
  
  let currentCategory = 'all';
  let searchQuery = '';

  async function renderGrid() {
    grid.innerHTML = '';
    const allOpps = await window.getOpportunities();
    const today = new Date().toISOString().split('T')[0];
    
    // Filter out expired, and apply category/search filters
    const filtered = allOpps.filter(opp => {
      // Expiry Logic
      if (opp.deadline && opp.deadline < today) return false; 
      
      // Category filter
      if (currentCategory !== 'all' && opp.category !== currentCategory) return false;
      
      // Search filter
      if (searchQuery) {
        const query = searchQuery.toLowerCase();
        const matchesTitle = opp.title.toLowerCase().includes(query);
        const matchesOrg = opp.organization.toLowerCase().includes(query);
        const matchesDesc = opp.description.toLowerCase().includes(query);
        if (!matchesTitle && !matchesOrg && !matchesDesc) return false;
      }
      
      return true;
    });

    if (filtered.length === 0) {
      grid.innerHTML = `
        <div style="grid-column: 1/-1; text-align:center; padding: 3rem; color: var(--text-secondary);">
          <h3>No opportunities found</h3>
          <p>Try adjusting your search or filters.</p>
        </div>
      `;
      return;
    }

    filtered.forEach(opp => {
      // Calculate days left
      let deadlineText = 'No deadline';
      let isUrgent = false;
      if (opp.deadline) {
        const d1 = new Date(today);
        const d2 = new Date(opp.deadline);
        const diffTime = Math.abs(d2 - d1);
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        
        if (diffDays <= 7) {
          isUrgent = true;
          deadlineText = `Closing in ${diffDays} day${diffDays > 1 ? 's' : ''}`;
        } else {
          deadlineText = `Closes: ${new Date(opp.deadline).toLocaleDateString('en-GB')}`;
        }
      }

      // Resolve link to source_url fallback if it's a generic root URL
      let displayLink = opp.link || opp.source_url || '#';
      try {
        if (displayLink && displayLink !== '#') {
          const u = new URL(displayLink.trim());
          if ((u.pathname === '/' || u.pathname === '') && !u.search && opp.source_url) {
            displayLink = opp.source_url.trim();
          }
        }
      } catch (e) {}

      const card = document.createElement('div');
      card.className = 'card';
      card.innerHTML = `
        <div class="card-header">
          <span class="card-category">${opp.category}</span>
          <span class="card-deadline ${isUrgent ? 'urgent' : ''}">
            ${isUrgent ? '⚠️ ' : '📅 '} ${deadlineText}
          </span>
        </div>
        <h3 class="card-title">${opp.title}</h3>
        <div class="card-org">${opp.organization}</div>
        <p class="card-desc">${opp.description}</p>
        <div class="card-footer">
          <a href="${displayLink}" target="_blank" class="btn btn-primary">Apply / More Info</a>
        </div>
      `;
      grid.appendChild(card);
    });
  }

  // Event Listeners for Tabs
  tabs.forEach(tab => {
    tab.addEventListener('click', (e) => {
      tabs.forEach(t => t.classList.remove('active'));
      e.target.classList.add('active');
      currentCategory = e.target.dataset.category;
      renderGrid();
    });
  });

  // Event Listener for Search
  searchInput.addEventListener('input', (e) => {
    searchQuery = e.target.value;
    renderGrid();
  });

  // Initial render
  renderGrid();
});
