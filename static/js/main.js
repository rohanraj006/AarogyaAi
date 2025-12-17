// static/js/main.js

// ==========================================
// 1. GLOBAL ACTIONS (Available everywhere)
// ==========================================

// --- APPOINTMENTS: Activate Link ---
window.activateLink = (apptId) => {
    if (!apptId) return;
    Swal.fire({
        title: 'Activate Link?',
        text: "Patient will be able to join the call.",
        icon: 'question',
        showCancelButton: true,
        confirmButtonText: 'Yes, Activate'
    }).then((result) => {
        if (result.isConfirmed) {
            fetch(`/appointments/activate/${apptId}`, { method: 'POST' })
                .then(res => {
                    if (res.ok) {
                        Swal.fire('Activated!', 'Link is live.', 'success');
                        if (typeof window.loadAppointmentsList === 'function') {
                            loadAppointmentsList('doctor');
                        } else {
                            location.reload();
                        }
                    } else {
                        Swal.fire('Error', 'Could not activate.', 'error');
                    }
                });
        }
    });
};

// --- APPOINTMENTS: Complete ---
window.completeAppointment = (apptId) => {
    if (!apptId) return;
    Swal.fire({
        title: 'Complete Appointment?',
        text: "This will mark the session as finished and deactivate the link.",
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Yes, Complete',
        confirmButtonColor: '#3085d6'
    }).then((result) => {
        if (result.isConfirmed) {
            fetch(`/appointments/complete/${apptId}`, { method: 'POST' })
                .then(res => {
                    if (res.ok) {
                        Swal.fire('Completed!', 'Appointment closed.', 'success');
                        if (typeof window.loadAppointmentsList === 'function') {
                            loadAppointmentsList('doctor');
                        } else {
                            location.reload();
                        }
                    } else {
                        Swal.fire('Error', 'Could not complete appointment.', 'error');
                    }
                });
        }
    });
};

// --- DOCTOR: Confirm/Reject Requests ---
window.confirmAppointment = (id) => {
    Swal.fire({
        title: 'Confirm Appointment',
        text: 'Select date and time:',
        html: '<input type="datetime-local" id="appt-time" class="swal2-input">',
        showCancelButton: true,
        confirmButtonText: 'Confirm',
        preConfirm: () => {
            const val = document.getElementById('appt-time').value;
            if (!val) Swal.showValidationMessage('Please select a time');
            return val;
        }
    }).then((result) => {
        if (result.isConfirmed) {
            fetch('/appointments/confirm', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ request_id: id, appointment_time: result.value })
            }).then(res => {
                if (res.ok) {
                    Swal.fire('Confirmed!', 'Appointment scheduled.', 'success').then(() => window.location.reload());
                } else {
                    res.json().then(data => Swal.fire('Error', data.detail || 'Could not confirm.', 'error'));
                }
            });
        }
    });
};

window.rejectAppointment = (id) => {
    Swal.fire({
        title: 'Reject Request?',
        text: "This cannot be undone.",
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Yes, Reject',
        confirmButtonColor: '#d33'
    }).then((result) => {
        if (result.isConfirmed) {
            fetch('/appointments/reject', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ request_id: id })
            }).then(res => {
                if (res.ok) {
                    Swal.fire('Rejected', 'Request removed.', 'success').then(() => window.location.reload());
                } else {
                    Swal.fire('Error', 'Could not reject.', 'error');
                }
            });
        }
    });
};

// --- PATIENT: Handle Connection Requests ---
window.handleConnection = (id, action) => {
    const url = action === 'accept' ? `/connections/requests/accept/${id}` : `/connections/requests/reject/${id}`;
    const method = action === 'accept' ? 'GET' : 'POST';
    
    fetch(url, { method: method })
        .then(res => {
            if (res.ok) {
                Swal.fire('Success', `Request ${action}ed.`, 'success').then(() => window.location.reload());
            } else {
                Swal.fire('Error', 'Action failed.', 'error');
            }
        });
};

// --- REPORTS: View Content Popup ---
window.viewReportPopup = async (contentId) => {
    if(!contentId) return;
    Swal.fire({
        title: 'Loading Report...',
        didOpen: () => { Swal.showLoading(); }
    });
    
    try {
        const res = await fetch(`/doctor/report/content/${contentId}`);
        const data = await res.json();
        
        const formattedContent = data.content ? data.content.replace(/\n/g, '<br>') : "No content available.";
        
        Swal.fire({
            title: 'Report Content',
            html: `<div class="text-left font-mono text-sm max-h-[60vh] overflow-y-auto p-2 bg-gray-50 border rounded">${formattedContent}</div>`,
            width: '800px',
            showCloseButton: true,
            showConfirmButton: false
        });
    } catch(e) {
        Swal.fire('Error', 'Failed to load report content.', 'error');
    }
};

// --- REPORTS: Delete Report ---
window.deleteReport = (reportId) => {
    Swal.fire({
        title: 'Delete Report?',
        text: "This cannot be undone.",
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#d33',
        confirmButtonText: 'Yes, delete it!'
    }).then((result) => {
        if (result.isConfirmed) {
            fetch(`/reports/${reportId}`, { method: 'DELETE' })
                .then(res => {
                    if (res.ok) {
                        Swal.fire('Deleted!', 'Your file has been deleted.', 'success');
                        // Use the globally exposed load function if available
                        if (typeof window.loadPatientReports === 'function') {
                            window.loadPatientReports();
                        } else {
                            location.reload();
                        }
                    } else {
                        Swal.fire('Error', 'Could not delete report.', 'error');
                    }
                });
        }
    });
};


// ==========================================
// 2. PAGE LOAD LOGIC (DOMContentLoaded)
// ==========================================

document.addEventListener("DOMContentLoaded", function() {

    // --- FORM HANDLING ---
    const handleFormSubmit = (formElement) => {
        if (!formElement) return;
        formElement.addEventListener("submit", function(event) {
            event.preventDefault();
            const formData = new FormData(formElement);
            const body = new URLSearchParams(formData);

            fetch(formElement.action, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: body
            })
            .then(response => {
                if (!response.ok) return response.json().then(err => { throw err; });
                return response.json();
            })
            .then(data => {
                Swal.fire({
                    icon: 'success',
                    title: 'Success!',
                    text: data.message || 'Operation successful!',
                    timer: 2000,
                    showConfirmButton: false
                }).then(() => {
                    if (data.user_type === 'doctor') window.location.href = '/doctor/dashboard';
                    else window.location.href = '/profile';
                });
            })
            .catch(error => {
                Swal.fire({ icon: 'error', title: 'Error', text: error.detail || 'An error occurred.' });
            });
        });
    };

    handleFormSubmit(document.getElementById("loginForm"));
    handleFormSubmit(document.getElementById("registerForm"));
    handleFormSubmit(document.getElementById("registerDoctorForm"));

    // --- LOGOUT ---
    const handleLogout = () => {
        fetch('/users/logout', { method: 'POST' }).then(res => { if (res.ok) window.location.href = '/'; });
    };
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) logoutBtn.addEventListener('click', handleLogout);
    const mobileLogout = document.getElementById('mobileLogout');
    if (mobileLogout) mobileLogout.addEventListener('click', handleLogout);

    // --- DOCTOR DASHBOARD: MY PATIENTS LIST ---
    const patientListContainer = document.getElementById("patient-list-container");
    if (patientListContainer) {
        fetch('/doctor/my-patients').then(res => res.json()).then(patients => {
            const loader = document.getElementById("patient-list-loader");
            if(loader) loader.style.display = 'none';
            
            if (!patients || patients.length === 0) {
                patientListContainer.innerHTML = '<p class="text-center text-gray-500">No connected patients.</p>';
                return;
            }
            let html = '<ul class="divide-y divide-gray-200">';
            patients.forEach(p => {
                html += `
                    <li class="py-4 flex justify-between items-center">
                      <div>
                        <p class="text-sm font-medium text-gray-900">${p.name.first} ${p.name.last}</p>
                        <p class="text-xs text-gray-400">ID: ${p.aarogya_id}</p>
                      </div>
                      <a href="/doctor/patient/${p.aarogya_id}" class="text-sm text-indigo-600 hover:text-indigo-500 font-semibold">View Records &rarr;</a>
                    </li>`;
            });
            html += '</ul>';
            patientListContainer.innerHTML = html;
        });
    }

    // --- PATIENT DASHBOARD: CONNECTION REQUESTS ---
    const connectionRequestsContainer = document.getElementById("connection-requests-container");
    if (connectionRequestsContainer) {
        fetch('/connections/requests/pending')
            .then(res => res.json())
            .then(requests => {
                const loader = document.getElementById("requests-loader");
                if(loader) loader.style.display = 'none';

                if (!requests || requests.length === 0) {
                    connectionRequestsContainer.innerHTML = '<p class="text-center text-gray-500 italic">No pending connection requests.</p>';
                    return;
                }
                
                let html = '<ul class="divide-y divide-gray-200">';
                requests.forEach(req => {
                    const reqId = req.id || req._id;
                    html += `
                        <li class="py-4 flex flex-col sm:flex-row justify-between items-center gap-4">
                          <div>
                            <p class="text-sm font-medium text-gray-900">Request from Doctor</p>
                            <p class="text-xs text-gray-500">${req.doctor_email}</p>
                          </div>
                          <div class="flex gap-2">
                             <button onclick="handleConnection('${reqId}', 'accept')" class="px-4 py-2 bg-green-600 text-white text-xs rounded-lg hover:bg-green-700 shadow-sm">Accept</button>
                             <button onclick="handleConnection('${reqId}', 'reject')" class="px-4 py-2 bg-white border border-gray-300 text-gray-700 text-xs rounded-lg hover:bg-gray-50 shadow-sm">Reject</button>
                          </div>
                        </li>`;
                });
                html += '</ul>';
                connectionRequestsContainer.innerHTML = html;
            });
    }

    // --- DOCTOR APPOINTMENTS: PENDING REQUESTS ---
    const pendingRequestsContainer = document.getElementById("pending-requests-container");
    if (pendingRequestsContainer) {
         fetch('/appointments/pending')
            .then(res => res.json())
            .then(data => {
                const loader = document.getElementById("pending-loader");
                if(loader) loader.style.display = 'none';

                if (!data || data.length === 0) {
                    pendingRequestsContainer.innerHTML = '<p class="text-gray-500 text-center text-sm py-4">No pending requests.</p>';
                    return;
                }
                pendingRequestsContainer.innerHTML = '';
                data.forEach(req => {
                    const reqId = req.id || req._id;
                    const card = document.createElement('div');
                    card.className = 'bg-white p-4 rounded-lg shadow-sm border border-yellow-100 mb-3';
                    card.innerHTML = `
                        <div class="flex justify-between items-start mb-2">
                             <div>
                                <p class="font-bold text-gray-800 text-sm">${req.patient_email}</p>
                                <p class="text-xs text-gray-500 mt-1">Severity: <span class="font-semibold text-indigo-600">${req.predicted_severity || 'Normal'}</span></p>
                             </div>
                             <span class="bg-yellow-100 text-yellow-800 text-xs px-2 py-1 rounded font-bold uppercase">Pending</span>
                        </div>
                        <div class="mb-3">
                            <p class="text-sm text-gray-700"><strong>Reason:</strong> ${req.reason}</p>
                            ${req.patient_notes ? `<p class="text-xs text-gray-500 mt-1 italic">"${req.patient_notes}"</p>` : ''}
                        </div>
                        <div class="flex gap-2">
                            <button onclick="confirmAppointment('${reqId}')" class="flex-1 bg-indigo-600 text-white py-2 rounded text-xs font-semibold hover:bg-indigo-700 transition">Confirm</button>
                            <button onclick="rejectAppointment('${reqId}')" class="flex-1 bg-white border border-red-200 text-red-600 py-2 rounded text-xs font-semibold hover:bg-red-50 transition">Reject</button>
                        </div>
                    `;
                    pendingRequestsContainer.appendChild(card);
                });
            });
    }

    // --- APPOINTMENTS LIST (SHARED: UPCOMING / HISTORY) ---
    window.loadAppointmentsList = (userType) => {
        const containerId = userType === 'doctor' ? 'upcoming-appointments-container' : 'my-appointments-container';
        const loaderId = userType === 'doctor' ? 'upcoming-loader' : 'my-appt-loader';
        const container = document.getElementById(containerId);
        const loader = document.getElementById(loaderId);

        if (!container) return;

        fetch('/appointments/list').then(res => res.json()).then(data => {
            if (loader) loader.style.display = 'none';
            
            let appointmentsToShow = data;
            // Doctor: Show confirmed/completed in "Upcoming/History" section
            if (userType === 'doctor') {
                appointmentsToShow = data.filter(a => a.status && (a.status.toLowerCase() === 'confirmed' || a.status.toLowerCase() === 'completed'));
            }

            if (appointmentsToShow.length === 0) {
                container.innerHTML = '<p class="text-gray-500 text-center py-4">No appointments found.</p>';
                return;
            }

            container.innerHTML = ''; 
            appointmentsToShow.forEach(appt => {
                const apptId = appt.id || appt._id; 
                const dateStr = appt.appointment_time ? new Date(appt.appointment_time).toLocaleString() : 'Date Pending';
                const otherParty = userType === 'doctor' ? `Patient: ${appt.patient_email}` : `Dr. ${appt.doctor_email}`;
                
                let statusColor = 'bg-gray-100 text-gray-800';
                const statusLower = (appt.status || 'pending').toLowerCase();
                
                if (statusLower === 'confirmed') statusColor = 'bg-green-100 text-green-800';
                if (statusLower === 'rejected') statusColor = 'bg-red-100 text-red-800';
                if (statusLower === 'completed') statusColor = 'bg-blue-100 text-blue-800';

                let actionButtons = '';

                // DOCTOR ACTIONS
                if (userType === 'doctor' && statusLower === 'confirmed') {
                    if(appt.meeting_link) {
                        actionButtons += `
                            <a href="${appt.meeting_link}" target="_blank" class="mt-2 block w-full text-center border border-green-600 text-green-600 py-2 rounded-lg text-sm hover:bg-green-50 transition-colors font-semibold">
                                Join Video Call
                            </a>`;
                    }
                    if (!appt.is_link_active) {
                        actionButtons += `
                            <button onclick="activateLink('${apptId}')" class="mt-2 block w-full text-center bg-indigo-600 text-white py-2 rounded-lg text-sm hover:bg-indigo-700 transition-colors shadow-sm">
                                Activate Link for Patient
                            </button>`;
                    } else {
                        actionButtons += `
                            <div class="mt-2 text-center text-xs text-green-700 bg-green-50 py-2 rounded border border-green-200 font-medium">
                                ✓ Link Active
                            </div>`;
                    }
                    actionButtons += `
                        <button onclick="completeAppointment('${apptId}')" class="mt-2 block w-full text-center border border-gray-300 text-gray-600 py-2 rounded-lg text-sm hover:bg-gray-100 transition-colors">
                            Mark Completed
                        </button>`;
                }

                // PATIENT ACTIONS
                if (userType === 'patient' && statusLower === 'confirmed') {
                    if (appt.is_link_active) {
                        actionButtons += `
                            <a href="${appt.meeting_link}" target="_blank" class="mt-3 block w-full text-center bg-green-600 text-white py-2 rounded-lg text-sm hover:bg-green-700 transition-colors font-bold shadow-md animate-pulse">
                                Join Video Call
                            </a>`;
                    } else {
                        actionButtons += `
                            <div class="mt-3 block w-full text-center bg-gray-100 text-gray-500 py-2 rounded-lg text-sm border border-gray-200 cursor-not-allowed">
                                Waiting for Doctor to Activate...
                            </div>`;
                    }
                }

                const card = document.createElement('div');
                card.className = 'p-4 border rounded-xl bg-white shadow-sm hover:shadow-md transition-shadow mb-4';
                card.innerHTML = `
                    <div class="flex justify-between items-start mb-2">
                        <div>
                            <p class="font-semibold text-gray-900 text-sm">${otherParty}</p>
                            ${appt.predicted_severity ? `<p class="text-xs text-gray-500 font-mono mt-1">Severity: ${appt.predicted_severity}</p>` : ''}
                        </div>
                        <span class="px-2 py-1 rounded text-xs font-bold uppercase ${statusColor}">${appt.status}</span>
                    </div>
                    <div class="text-sm text-gray-700 space-y-1 mb-3">
                        <p><strong>Reason:</strong> ${appt.reason}</p>
                        <p><span class="font-medium">Time:</span> ${dateStr}</p>
                    </div>
                    ${actionButtons}
                `;
                container.appendChild(card);
            });
        }).catch(err => { if(loader) loader.innerText = 'Error loading.'; });
    };

    if (document.getElementById('patient-appointments-view')) loadAppointmentsList('patient');
    if (document.getElementById('doctor-appointments-view')) loadAppointmentsList('doctor');

    // --- CHAT WIDGET HANDLING ---
    document.body.addEventListener('submit', async function(e) {
        if (e.target && e.target.id === 'chatForm') {
            if (e.target.closest('#chatPanel')) {
                e.preventDefault();
                const form = e.target;
                const input = form.querySelector('input[name="query"]');
                const message = input.value.trim();
                
                if (!message) return;

                const container = document.getElementById('chat-messages');
                
                const userMsgHtml = `
                    <div class="flex justify-end mb-2 animate-message-entry">
                        <div class="bg-indigo-600 text-white px-3 py-2 rounded-lg rounded-tr-none text-sm max-w-[85%] shadow-sm">
                            ${message}
                        </div>
                    </div>`;
                container.insertAdjacentHTML('beforeend', userMsgHtml);
                container.scrollTop = container.scrollHeight;

                const formData = new FormData(form);
                input.value = '';

                try {
                    const response = await fetch('/ai/chat', { method: 'POST', body: formData });
                    if (!response.ok) throw new Error("Network response was not ok");
                    const html = await response.text();
                    container.insertAdjacentHTML('beforeend', html);
                    container.scrollTop = container.scrollHeight;
                } catch (err) {
                    console.error(err);
                    container.insertAdjacentHTML('beforeend', `<div class="text-xs text-red-500 text-center mt-2">Error sending message.</div>`);
                }
            }
        }
    });

    // ==========================================
    // DOCTOR: VIEW PATIENT RECORDS (Specific Page)
    // ==========================================
    // RENAMED VARIABLE TO AVOID CONFLICT
    const docReportContainer = document.getElementById("doctor-patient-report-list");
    if (docReportContainer) {
        const patientId = docReportContainer.getAttribute("data-patient-id");
        if (patientId) {
            
            // 1. Fetch Reports
            fetch(`/doctor/patient/${patientId}/reports`)
                .then(res => res.json())
                .then(reports => {
                    const loader = document.getElementById("doc-report-loader");
                    if (loader) loader.style.display = 'none';

                    if (!reports || reports.length === 0) {
                        docReportContainer.innerHTML = '<div class="p-6 bg-gray-50 border border-dashed rounded-xl text-center"><p class="text-gray-500 italic">No reports uploaded for this patient.</p></div>';
                        return;
                    }

                    let html = '<div class="grid gap-4">';
                    reports.forEach(report => {
                         const dateStr = report.date ? new Date(report.date).toLocaleDateString() : 'Unknown Date';
                         const reportType = report.report_type || 'General';
                         const description = report.description || 'No description';
                         const contentId = report.content_id;
                         
                         html += `
                            <div class="bg-gray-50 border border-gray-200 rounded-xl p-4 flex justify-between items-center hover:shadow-sm transition">
                                <div class="flex items-center gap-3">
                                    <div class="bg-indigo-100 text-indigo-600 p-2 rounded-lg">
                                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                                    </div>
                                    <div>
                                        <div class="flex items-center gap-2 mb-1">
                                            <p class="font-bold text-gray-800 text-sm">${reportType}</p>
                                            <span class="text-xs text-gray-400 bg-white border px-2 rounded-full">${dateStr}</span>
                                        </div>
                                        <p class="text-xs text-gray-500 truncate max-w-md">${description}</p>
                                    </div>
                                </div>
                                <button onclick="viewReportPopup('${contentId}')" class="px-4 py-2 bg-white text-indigo-600 border border-gray-200 rounded-lg text-sm font-medium hover:bg-indigo-50 hover:border-indigo-200 transition">
                                    View
                                </button>
                            </div>
                         `;
                    });
                    html += '</div>';
                    docReportContainer.innerHTML = html;
                })
                .catch(err => {
                    console.error(err);
                    docReportContainer.innerHTML = '<p class="text-red-500 bg-red-50 p-4 rounded text-center">Error loading reports.</p>';
                });

            // 2. Fetch Patient Details (Sidebar)
            const detailsContainer = document.getElementById("patient-details-container");
            if (detailsContainer) {
                 fetch(`/doctor/api/patients/search?aarogya_id=${patientId}`)
                    .then(res => res.json())
                    .then(data => {
                        const val = (v) => v || '<span class="text-gray-400 italic">N/A</span>';
                        detailsContainer.innerHTML = `
                            <div class="space-y-3">
                                <div>
                                    <p class="text-xs text-gray-500 uppercase font-bold">Full Name</p>
                                    <p class="text-lg font-bold text-gray-800">${data.name.first} ${data.name.last}</p>
                                </div>
                                <div class="grid grid-cols-2 gap-4">
                                    <div>
                                        <p class="text-xs text-gray-500 uppercase font-bold">Age</p>
                                        <p class="font-medium">${val(data.age)}</p>
                                    </div>
                                    <div>
                                        <p class="text-xs text-gray-500 uppercase font-bold">Gender</p>
                                        <p class="font-medium">${val(data.gender)}</p>
                                    </div>
                                </div>
                                <div>
                                    <p class="text-xs text-gray-500 uppercase font-bold">Contact</p>
                                    <p class="font-medium text-indigo-600">${val(data.phone_number)}</p>
                                    <p class="text-xs text-gray-400">${val(data.email)}</p>
                                </div>
                                <div class="pt-2 border-t">
                                    <p class="text-xs text-gray-500 uppercase font-bold mb-1">Medical Profile</p>
                                    <div class="flex flex-wrap gap-2">
                                        <span class="px-2 py-1 bg-red-50 text-red-700 text-xs rounded border border-red-100">Blood: ${val(data.blood_group)}</span>
                                    </div>
                                </div>
                            </div>
                        `;
                    });
            }
        }
    }

    // ==========================================
    // PATIENT: MY REPORTS PAGE
    // ==========================================
    // RENAMED VARIABLE TO AVOID CONFLICT
    const patientReportContainer = document.getElementById("report-list-container");
    const structuredRecordContainer = document.getElementById("structured-record-container");
    const uploadReportForm = document.getElementById("uploadReportForm");

    // 1. Upload Report Handler
    if (uploadReportForm) {
        uploadReportForm.addEventListener("submit", function(e) {
            e.preventDefault();
            const formData = new FormData(uploadReportForm);
            
            const btn = uploadReportForm.querySelector('button');
            const originalText = btn.innerText;
            btn.innerText = 'Uploading...';
            btn.disabled = true;

            fetch('/reports/upload', {
                method: 'POST',
                body: formData
            })
            .then(res => res.json())
            .then(data => {
                if(data.message) {
                    Swal.fire('Success', data.message, 'success');
                    uploadReportForm.reset();
                    window.loadPatientReports(); 
                } else {
                    Swal.fire('Error', 'Upload failed.', 'error');
                }
            })
            .catch(err => Swal.fire('Error', 'Network error.', 'error'))
            .finally(() => {
                btn.innerText = originalText;
                btn.disabled = false;
            });
        });
    }

    // 2. Function to Load Patient Reports (Calls /reports/my-reports)
    window.loadPatientReports = () => {
        if (!patientReportContainer) return;
        
        fetch('/reports/my-reports')
            .then(res => res.json())
            .then(reports => {
                const loader = document.getElementById("report-loader");
                if(loader) loader.style.display = 'none';

                if (!reports || reports.length === 0) {
                    patientReportContainer.innerHTML = '<p class="text-gray-500 text-center py-4">No reports uploaded yet.</p>';
                    return;
                }

                let html = '<div class="space-y-3">';
                reports.forEach(r => {
                    const reportId = r.id || r._id;
                    const dateStr = r.upload_date ? new Date(r.upload_date).toLocaleDateString() : 'Unknown Date';
                    
                    html += `
                        <div class="flex items-center justify-between p-4 bg-gray-50 rounded-lg border hover:shadow-sm transition">
                            <div class="flex items-center gap-3">
                                <div class="bg-indigo-100 text-indigo-600 p-2 rounded">
                                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                                </div>
                                <div>
                                    <p class="font-medium text-gray-900">${r.filename}</p>
                                    <p class="text-xs text-gray-500">${r.report_type} • ${dateStr}</p>
                                </div>
                            </div>
                            <div class="flex gap-2">
                                <a href="/reports/${reportId}/download" class="text-sm text-indigo-600 hover:underline flex items-center gap-1">
                                    Download
                                </a>
                                <button onclick="deleteReport('${reportId}')" class="text-sm text-red-500 hover:text-red-700">
                                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                                </button>
                            </div>
                        </div>`;
                });
                html += '</div>';
                patientReportContainer.innerHTML = html;
            });
    };

    // 3. Load Structured Medical Record (Summary)
    if (structuredRecordContainer) {
        fetch('/reports/my-structured-record')
            .then(res => res.json())
            .then(data => {
                const loader = document.getElementById("record-loader");
                if(loader) loader.style.display = 'none';

                if (!data) return;

                const createList = (items, emptyMsg) => {
                    if (!items || items.length === 0) return `<p class="text-gray-400 text-xs italic">${emptyMsg}</p>`;
                    return `<ul class="list-disc list-inside text-sm text-gray-700 space-y-1">${items.map(i => `<li>${typeof i === 'string' ? i : i.name || i.disease || i}</li>`).join('')}</ul>`;
                };

                structuredRecordContainer.innerHTML = `
                    <div class="space-y-4">
                        <div>
                            <h4 class="font-bold text-gray-700 text-sm">Allergies</h4>
                            ${createList(data.allergies, "No allergies recorded.")}
                        </div>
                        <div>
                            <h4 class="font-bold text-gray-700 text-sm">Conditions</h4>
                            ${createList(data.diagnoses, "No diagnoses recorded.")}
                        </div>
                        <div>
                            <h4 class="font-bold text-gray-700 text-sm">Medications</h4>
                            ${createList(data.current_medications, "No active medications.")}
                        </div>
                    </div>
                `;
            });
    }

    // TRIGGER LOAD: Call this if we are on the reports page
    if (patientReportContainer) loadPatientReports();

});