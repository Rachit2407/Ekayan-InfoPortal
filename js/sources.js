// js/sources.js
// Logic for managing scraper sources inside the admin panel.

let lastTestResult = null;

// Extend the admin tab switcher to handle the "sources" tab
if (typeof window.switchAdminTab === 'function') {
  const originalSwitch = window.switchAdminTab;
  window.switchAdminTab = function(tab) {
    // Hide/show the manage and review sections
    originalSwitch(tab);
    
    // Handle the new sources section
    const secSources = document.getElementById('section-sources');
    const tabSources = document.getElementById('tab-sources');
    
    if (secSources) secSources.style.display = tab === 'sources' ? '' : 'none';
    if (tabSources) tabSources.classList.toggle('active', tab === 'sources');
    
    if (tab === 'sources') {
      loadSources();
      resetAddForm();
    }
  };
}

// Reset the add new source form
function resetAddForm() {
  document.getElementById('src-url').value = '';
  document.getElementById('src-label').value = '';
  document.getElementById('src-keywords').value = '';
  document.getElementById('src-category').value = 'scholarships';
  
  const testResultsDiv = document.getElementById('test-results');
  testResultsDiv.innerHTML = '';
  testResultsDiv.style.display = 'none';
  
  const saveSection = document.getElementById('save-source-config');
  saveSection.style.display = 'none';
  
  const btnTest = document.getElementById('btn-test-src');
  if (btnTest) {
    btnTest.disabled = false;
    btnTest.textContent = '🔍 Test URL Compatibility';
  }
  
  lastTestResult = null;
}

// Load current sources from backend and render the table
async function loadSources() {
  const tableBody = document.getElementById('sources-table-body');
  if (!tableBody) return;
  
  tableBody.innerHTML = '<tr><td colspan="5" style="text-align:center;">Loading sources...</td></tr>';
  
  try {
    const res = await fetch('/list-sources');
    if (!res.ok) throw new Error('Failed to fetch sources');
    const data = await res.json();
    const sources = data.sources || [];
    
    if (sources.length === 0) {
      tableBody.innerHTML = '<tr><td colspan="5" style="text-align:center;">No sources configured. Add one above!</td></tr>';
      return;
    }
    
    tableBody.innerHTML = '';
    sources.forEach(src => {
      const tr = document.createElement('tr');
      
      const typeLabel = src.type === 'sitemap' ? '📄 Sitemap' : (src.type === 'category_page' ? '📁 Category Page' : '🔗 Direct Link');
      const keywords = src.link_filter_keywords ? src.link_filter_keywords.join(', ') : 'None';
      
      tr.innerHTML = `
        <td>
          <strong>${src.label}</strong>
          <div style="font-size:0.8rem; color:var(--text-secondary); word-break:break-all; margin-top:2px;">
            <a href="${src.url}" target="_blank" style="color:var(--primary-color);">${src.url}</a>
          </div>
        </td>
        <td><span class="card-category" style="padding: 2px 8px; font-size: 0.8rem; text-transform: capitalize;">${src.category_hint || 'scholarships'}</span></td>
        <td><span style="font-size:0.85rem;">${typeLabel}</span></td>
        <td><code style="font-size:0.8rem; background:rgba(255,255,255,0.05); padding:2px 4px; border-radius:4px;">${keywords}</code></td>
        <td>
          <button class="btn btn-danger btn-sm btn-delete-src" data-url="${src.url}" style="padding: 5px 10px; font-size: 0.8rem;">🗑️ Remove</button>
        </td>
      `;
      tableBody.appendChild(tr);
    });

    // Attach event listeners to delete buttons
    document.querySelectorAll('.btn-delete-src').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const url = e.target.closest('button').dataset.url;
        deleteSource(url);
      });
    });

  } catch (err) {
    console.error(err);
    tableBody.innerHTML = '<tr><td colspan="5" style="text-align:center; color:var(--danger);">Error loading sources. Make sure server is running.</td></tr>';
  }
}

// Trigger URL compatibility test
async function testSourceUrl() {
  const urlInput = document.getElementById('src-url').value.trim();
  const keywordsInput = document.getElementById('src-keywords').value.trim();
  
  if (!urlInput) {
    alert('Please enter a website URL to test.');
    return;
  }
  
  const btnTest = document.getElementById('btn-test-src');
  btnTest.disabled = true;
  btnTest.textContent = '⏳ Testing Compatibility...';
  
  const testResultsDiv = document.getElementById('test-results');
  testResultsDiv.innerHTML = '<p style="text-align:center; color:var(--text-secondary);">Analyzing page structure and discovering links...</p>';
  testResultsDiv.style.display = 'block';
  
  try {
    const res = await fetch('/test-source', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: urlInput,
        filter_keywords: keywordsInput
      })
    });
    
    if (!res.ok) throw new Error('Test request failed');
    const result = await res.json();
    
    btnTest.disabled = false;
    btnTest.textContent = '🔍 Test URL Compatibility';
    
    if (result.success) {
      lastTestResult = result;
      
      const typeText = result.type === 'sitemap' ? 'XML Sitemap Index' : 'HTML Category Listing Page';
      
      if (result.count > 0) {
        const urlsHtml = result.discovered_urls.map(u => `<li style="margin-bottom:4px; word-break:break-all;"><a href="${u}" target="_blank" style="color:var(--primary-color);">${u}</a></li>`).join('');
        testResultsDiv.innerHTML = `
          <div style="border-left: 4px solid var(--success); padding-left: 10px; margin-bottom: 10px;">
            <p style="color:var(--success); font-weight:bold; margin-bottom:4px;">✅ Compatibility Pass!</p>
            <p style="font-size:0.9rem; margin-bottom:8px;">Detected: <strong>${typeText}</strong></p>
            <p style="font-size:0.9rem; margin-bottom:4px;">Found <strong>${result.count}</strong> sample pages to scan:</p>
            <ul style="font-size:0.85rem; padding-left:20px; color:var(--text-secondary);">
              ${urlsHtml}
            </ul>
          </div>
        `;
        
        // Show save configuration section
        document.getElementById('save-source-config').style.display = 'block';
        
        // Auto-suggest label from domain name
        try {
          const domain = new URL(urlInput).hostname.replace('www.', '');
          document.getElementById('src-label').value = domain.split('.')[0].charAt(0).toUpperCase() + domain.split('.')[0].slice(1) + ' Opportunities';
        } catch (e) {}
      } else {
        testResultsDiv.innerHTML = `
          <div style="border-left: 4px solid var(--warning); padding-left: 10px;">
            <p style="color:var(--warning); font-weight:bold; margin-bottom:4px;">⚠️ No Links Discovered</p>
            <p style="font-size:0.9rem; color:var(--text-secondary);">
              The website structure was fetched but no relevant links were discovered. This site may be using JavaScript to render content or require custom developer settings.
            </p>
          </div>
        `;
        document.getElementById('save-source-config').style.display = 'none';
      }
    } else {
      testResultsDiv.innerHTML = `
        <div style="border-left: 4px solid var(--danger); padding-left: 10px;">
          <p style="color:var(--danger); font-weight:bold; margin-bottom:4px;">❌ Analysis Failed</p>
          <p style="font-size:0.9rem; color:var(--text-secondary);">${result.error || 'Connection timed out or failed.'}</p>
        </div>
      `;
      document.getElementById('save-source-config').style.display = 'none';
    }
  } catch (err) {
    btnTest.disabled = false;
    btnTest.textContent = '🔍 Test URL Compatibility';
    testResultsDiv.innerHTML = `
      <div style="border-left: 4px solid var(--danger); padding-left: 10px;">
        <p style="color:var(--danger); font-weight:bold; margin-bottom:4px;">❌ Connection Error</p>
        <p style="font-size:0.9rem; color:var(--text-secondary);">Could not connect to the backend server. Make sure "python server.py" is running.</p>
      </div>
    `;
    document.getElementById('save-source-config').style.display = 'none';
  }
}

// Save verified source to scraper configuration
async function saveSourceToScraper() {
  const urlInput = document.getElementById('src-url').value.trim();
  const labelInput = document.getElementById('src-label').value.trim();
  const categoryHint = document.getElementById('src-category').value;
  const keywordsInput = document.getElementById('src-keywords').value.trim();
  
  if (!urlInput || !labelInput) {
    alert('Please provide a label and URL.');
    return;
  }
  
  if (!lastTestResult) {
    alert('Please test the URL successfully first.');
    return;
  }
  
  try {
    const res = await fetch('/save-source', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: urlInput,
        label: labelInput,
        category_hint: categoryHint,
        type: lastTestResult.type,
        link_filter_keywords: keywordsInput
      })
    });
    
    const result = await res.json();
    if (res.ok && result.success) {
      alert('🎉 Scraper source saved successfully!');
      resetAddForm();
      loadSources();
    } else {
      alert('❌ Failed to save source: ' + (result.error || 'Unknown error'));
    }
  } catch (err) {
    console.error(err);
    alert('❌ Error saving source. Check console.');
  }
}

// Delete a source
async function deleteSource(url) {
  if (!confirm(`Are you sure you want to remove this website from the scraper?`)) {
    return;
  }
  
  try {
    const res = await fetch('/delete-source', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: url })
    });
    
    const result = await res.json();
    if (res.ok && result.success) {
      loadSources();
    } else {
      alert('❌ Failed to delete source: ' + (result.error || 'Unknown error'));
    }
  } catch (err) {
    console.error(err);
    alert('❌ Error deleting source.');
  }
}

// Init listener when script loads or DOMContentLoaded
document.addEventListener('DOMContentLoaded', () => {
  const btnTest = document.getElementById('btn-test-src');
  if (btnTest) {
    btnTest.addEventListener('click', testSourceUrl);
  }
  
  const btnSave = document.getElementById('btn-save-src');
  if (btnSave) {
    btnSave.addEventListener('click', saveSourceToScraper);
  }
});
