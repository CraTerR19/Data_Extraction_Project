
document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const idForm = document.getElementById('id-form');
    const userIdInput = document.getElementById('user-id');
    const btnSubmit = document.getElementById('btn-submit');

    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const browseBtn = document.getElementById('browse-btn');
    const fileNameDisplay = document.getElementById('file-name-display');
    const btnUpload = document.getElementById('btn-upload');

    const statusPanel = document.getElementById('status-panel');
    const statusText = document.getElementById('status-text');

    const resultsPanel = document.getElementById('results-panel');
    const resultsContent = document.getElementById('results-content');
    const btnCloseResults = document.getElementById('btn-close-results');

    let selectedFile = null;

    // --- ID Form Logic ---
    idForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const id = userIdInput.value.trim();
        if (!id) return;

        showStatus(`Saving ID to Database: ${id}...`);
        hideResults();

        try {
            const response = await fetch(`http://localhost:5000/api/submit-id`, { 
                method: 'POST', 
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id }) 
            });
            const data = await response.json();
            
            if (response.ok) {
                // Show a success message without the data table
                resultsContent.innerHTML = `
                    <div style="color: var(--success); font-weight: 500; display: flex; align-items: center; gap: 0.5rem; padding: 1rem; background: rgba(16, 185, 129, 0.1); border-radius: 8px;">
                        <i class="ph ph-check-circle" style="font-size: 1.2rem;"></i>
                        <span>${data.message || `ID ${id} has been securely registered.`}</span>
                    </div>
                `;
                resultsPanel.classList.remove('hidden');
                
                // We keep the ID in the input box so the PDF upload can use it!
                // userIdInput.value = '';
            } else {
                throw new Error(data.detail || data.error || "Failed to save ID.");
            }
        } catch (error) {
            renderError(error.message || "Failed to save ID. Please try again.");
        } finally {
            hideStatus();
        }
    });

    // --- Drag and Drop / File Selection Logic ---
    browseBtn.addEventListener('click', () => fileInput.click());

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) handleFile(e.target.files[0]);
    });
    
    // Clicking "Browse" forwards to the hidden file input and we handle the first selected file.

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            handleFile(e.dataTransfer.files[0]);
        }
    });

    function handleFile(file) {
        if (file.type !== 'application/pdf') {
            alert('Please upload a valid PDF file.');
            return;
        }
        selectedFile = file;
        fileNameDisplay.textContent = `Selected: ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`;
        btnUpload.disabled = false;
        hideResults();
    }

    // --- PDF Upload Logic ---
    btnUpload.addEventListener('click', async () => {
        if (!selectedFile) return;

        showStatus(`Uploading ${selectedFile.name} to Backend server & AWS S3...`);
        
        try {
            const formData = new FormData();
            formData.append('pdfDocument', selectedFile);
            
            // Send the user ID from Option 1 if entered, otherwise 'Unknown'
            let userId = 'Unknown';
            const option1Id = document.getElementById('user-id').value.trim();
            if (option1Id) {
                userId = option1Id;
            }
            formData.append('userId', userId);

            const response = await fetch('http://localhost:5000/api/upload-pdf', {
                method: 'POST',
                body: formData
            });
            const data = await response.json();
            
            if (response.ok && data.success) {
                renderResults(data.data, `Successfully processed Invoice!`);
                
                // Reset file state, but keep the user ID intact
                selectedFile = null;
                fileNameDisplay.textContent = '';
                fileInput.value = '';
                btnUpload.disabled = true;
            } else {
                throw new Error(data.detail || data.error || "Server processing failed.");
            }

        } catch (error) {
            renderError(error.message || "Failed to process document. Please try again.");
        } finally {
            hideStatus();
        }
    });

    btnCloseResults.addEventListener('click', hideResults);

    // --- UI Helpers ---
    function showStatus(message) {
        statusText.textContent = message;
        statusPanel.classList.remove('hidden');
    }

    function hideStatus() {
        statusPanel.classList.add('hidden');
    }

    function hideResults() {
        resultsPanel.classList.add('hidden');
    }

    function renderResults(data, successMsg) {
        let html = `<div style="margin-bottom: 1rem; color: var(--success); font-weight: 500;">
                        <i class="ph ph-check-circle"></i> ${successMsg}
                    </div>`;
        
        html += `<table class="data-table">
                    <thead>
                        <tr>
                            <th>Field</th>
                            <th>Value</th>
                        </tr>
                    </thead>
                    <tbody>`;
        
        let recordId = data['Record ID'] || null;

        for (const [key, value] of Object.entries(data)) {
            if (key === 'Record ID') continue;
            // format keys (e.g. patientName -> Patient Name)
            const formattedKey = key.replace(/([A-Z])/g, ' $1').replace(/^./, str => str.toUpperCase());
            
            // For values, use input fields mapped to their keys
            html += `<tr>
                        <td style="font-weight: 500; vertical-align: middle;">${formattedKey}</td>
                        <td style="color: var(--text-primary);">
                            <input type="text" id="edit-${key.replace(/\s+/g, '-')}" value="${value}" style="width: 100%; padding: 0.6rem; border: 1px solid var(--border, #e5e7eb); border-radius: 6px; background: rgba(255,255,255,0.7); color: inherit; font-family: inherit; font-size: 0.95rem; box-shadow: inset 0 1px 2px rgba(0,0,0,0.05);" />
                        </td>
                     </tr>`;
        }
        
        html += `</tbody></table>`;
        
        if (recordId) {
            html += `<div style="margin-top: 1.5rem; display: flex; justify-content: flex-end;">
                        <button type="button" class="btn btn-primary" id="btn-save-changes">
                            <span>Save Changes</span>
                            <i class="ph ph-floppy-disk"></i>
                        </button>
                     </div>`;
        }

        resultsContent.innerHTML = html;
        resultsPanel.classList.remove('hidden');
        resultsPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        
        if (recordId) {
            const btnSaveChanges = document.getElementById('btn-save-changes');
            if (btnSaveChanges) {
                btnSaveChanges.addEventListener('click', async () => {
                    await saveEditedInvoice(recordId);
                });
            }
        }
    }

    async function saveEditedInvoice(recordId) {
        const userId = document.getElementById('edit-User-ID')?.value || '';
        const invoiceNo = document.getElementById('edit-Invoice-Number')?.value || '';
        const dateVal = document.getElementById('edit-Date')?.value || '';
        const amount = document.getElementById('edit-Amount')?.value || '';
        
        showStatus('Saving changes to database...');
        try {
            const response = await fetch(`http://localhost:5000/api/update-invoice/${recordId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    "User ID": userId,
                    "Invoice Number": invoiceNo,
                    "Date": dateVal,
                    "Amount": amount
                })
            });
            const data = await response.json();
            
            if (response.ok && data.success) {
                // Re-render with updated success message but keeping the inputs intact
                const updatedData = {
                    "Record ID": recordId,
                    "User ID": userId,
                    "Invoice Number": invoiceNo,
                    "Date": dateVal,
                    "Amount": amount
                };
                renderResults(updatedData, data.message || "Changes successfully saved!");
            } else {
                throw new Error(data.detail || data.error || "Failed to update invoice");
            }
        } catch (error) {
            alert("Error saving changes: " + error.message);
        } finally {
            hideStatus();
        }
    }

    function renderError(message) {
        resultsContent.innerHTML = `
            <div style="color: var(--danger); background: rgba(239, 68, 68, 0.1); padding: 1rem; border-radius: 8px; display: flex; align-items: center; gap: 0.5rem;">
                <i class="ph ph-warning-circle" style="font-size: 1.2rem;"></i>
                <span>${message}</span>
            </div>
        `;
        resultsPanel.classList.remove('hidden');
    }
});
