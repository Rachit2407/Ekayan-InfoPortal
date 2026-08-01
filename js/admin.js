document.addEventListener('DOMContentLoaded', () => {
  // Login Overlay Logic
  const loginOverlay = document.getElementById('login-overlay');
  const btnLogin = document.getElementById('btn-login');
  const passwordInput = document.getElementById('admin-password');
  const loginError = document.getElementById('login-error');

  btnLogin.addEventListener('click', () => {
    if (passwordInput.value === 'admin123') {
      loginOverlay.style.display = 'none';
    } else {
      loginError.style.display = 'block';
    }
  });

  passwordInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') btnLogin.click();
  });

  // Admin Dashboard Logic
  const tableBody = document.getElementById('admin-table-body');
  const form = document.getElementById('opportunity-form');
  const formTitle = document.getElementById('form-title');
  const btnCancel = document.getElementById('btn-cancel');
  
  // Form fields
  const fId = document.getElementById('opp-id');
  const fTitle = document.getElementById('opp-title');
  const fCategory = document.getElementById('opp-category');
  const fOrg = document.getElementById('opp-org');
  const fDeadline = document.getElementById('opp-deadline');
  const fLink = document.getElementById('opp-link');
  const fDesc = document.getElementById('opp-desc');

  async function renderTable() {
    tableBody.innerHTML = '';
    const opps = await window.getOpportunities();
    
    if (opps.length === 0) {
      tableBody.innerHTML = `<tr><td colspan="4" class="empty-state">No opportunities available. Add one!</td></tr>`;
      return;
    }
    
    // Sort by deadline ascending
    opps.sort((a,b) => new Date(a.deadline) - new Date(b.deadline));

    opps.forEach(opp => {
      const today = new Date().toISOString().split('T')[0];
      const isExpired = opp.deadline && opp.deadline < today;
      
      const tr = document.createElement('tr');
      if (isExpired) tr.style.opacity = '0.5';
      
      tr.innerHTML = `
        <td>
          <strong>${opp.title}</strong><br>
          <span style="font-size:0.8rem; color:var(--text-secondary)">${opp.organization}</span>
        </td>
        <td><span class="card-category">${opp.category}</span></td>
        <td>
          ${opp.deadline ? new Date(opp.deadline).toLocaleDateString('en-GB') : 'N/A'}
          ${isExpired ? '<br><span style="color:var(--danger);font-size:0.75rem;">Expired</span>' : ''}
        </td>
        <td class="action-btns">
          <button class="btn btn-secondary btn-edit" data-id="${opp.id}" style="padding:0.3rem 0.6rem; font-size:0.8rem;">Edit</button>
          <button class="btn btn-danger btn-delete" data-id="${opp.id}" style="padding:0.3rem 0.6rem; font-size:0.8rem;">Delete</button>
        </td>
      `;
      tableBody.appendChild(tr);
    });

    // Attach listeners
    document.querySelectorAll('.btn-edit').forEach(btn => {
      btn.addEventListener('click', (e) => editItem(e.target.dataset.id));
    });
    
    document.querySelectorAll('.btn-delete').forEach(btn => {
      btn.addEventListener('click', (e) => deleteItem(e.target.dataset.id));
    });
  }

  async function editItem(id) {
    const opps = await window.getOpportunities();
    const item = opps.find(o => o.id === id);
    if (!item) return;

    formTitle.innerText = "Edit Opportunity";
    btnCancel.style.display = "inline-block";
    
    fId.value = item.id;
    fTitle.value = item.title;
    fCategory.value = item.category;
    fOrg.value = item.organization;
    fDeadline.value = item.deadline;
    fLink.value = item.link;
    fDesc.value = item.description;
    
    window.scrollTo(0, 0);
  }

  async function deleteItem(id) {
    if(!confirm('Are you sure you want to delete this opportunity?')) return;
    
    await window.deleteOpportunity(id);
    renderTable();
  }

  function resetForm() {
    form.reset();
    fId.value = '';
    formTitle.innerText = "Add New Opportunity";
    btnCancel.style.display = "none";
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const id = fId.value;
    
    const newOpp = {
      id: id ? id : 'opp-' + Date.now(),
      category: fCategory.value,
      title: fTitle.value,
      organization: fOrg.value,
      deadline: fDeadline.value,
      link: fLink.value,
      description: fDesc.value,
      status: 'approved'
    };

    await window.upsertOpportunity(newOpp);
    resetForm();
    renderTable();
  });

  btnCancel.addEventListener('click', resetForm);

  // Initial render
  renderTable();
});
