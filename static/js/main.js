document.addEventListener("DOMContentLoaded", function() {

    
    const handleFormSubmit = (formElement) => {
        if (!formElement) return;

        formElement.addEventListener("submit", function(event) {
            event.preventDefault();
            
            // 1. Get the form data
            const formData = new FormData(formElement);
            
            // 2. Convert it to the correct format (x-www-form-urlencoded)
            // This is the key fix for the registration routes!
            const body = new URLSearchParams(formData);

            fetch(formElement.action, {
                method: 'POST',
                headers: {
                    // 3. Explicitly set the Content-Type
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                // 4. Send the correct body format
                body: body
            })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(err => { throw err; });
                }
                return response.json();
            })
            .then(data => {
                Swal.fire({
                    icon: 'success',
                    title: 'Success!',
                    // The registration routes return the user object, login returns a message
                    text: data.message || 'Registration successful!', 
                    timer: 2000,
                    showConfirmButton: false
                }).then(() => {
                    // This redirect logic will now work for all forms
                    if (data.user_type === 'doctor') {
                        window.location.href = '/doctor/dashboard';
                    } else {
                        window.location.href = '/profile'; // Default for patients
                    }
                });
            })
            .catch(error => {
                Swal.fire({
                    icon: 'error',
                    title: 'Oops...',
                    text: error.detail || 'An unknown error occurred. Please check your input and try again.'
                });
            });
        });
    };

    // Attach the handler to all three forms
    handleFormSubmit(document.getElementById("loginForm"));
    handleFormSubmit(document.getElementById("registerForm"));
    handleFormSubmit(document.getElementById("registerDoctorForm"));


    // --- Logout Button Logic ---
    const handleLogout = () => {
        fetch('/users/logout', { method: 'POST' })
            .then(response => {
                if (response.ok) window.location.href = '/';
            });
    };

    const desktopLogoutBtn = document.getElementById('logoutBtn');
    if (desktopLogoutBtn) desktopLogoutBtn.addEventListener('click', handleLogout);

    const mobileLogoutBtn = document.getElementById('mobileLogout');
    if (mobileLogoutBtn) mobileLogoutBtn.addEventListener('click', handleLogout);

    const patientListContainer = document.getElementById("patient-list-container");

    if (patientListContainer) {
        // This code runs only on the doctor dashboard
        fetch('/doctor/my-patients')
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(patients => {
                // Hide the loader
                const loader = document.getElementById("patient-list-loader");
                if (loader) loader.style.display = 'none';

                if (patients.length === 0) {
                    patientListContainer.innerHTML = `
                        <p class="text-center text-gray-500">
                          No connected patients yet.
                        </p>
                    `;
                    return;
                }

                // Build the patient list HTML
                let patientHtml = '<ul class="divide-y divide-gray-200">';
                patients.forEach(patient => {
                    patientHtml += `
                        <li class="py-4 flex justify-between items-center">
                          <div>
                            <p class="text-sm font-medium text-gray-900">${patient.name ? patient.name.first + ' ' + patient.name.last : 'N/A'}</p>
                            <p class="text-sm text-gray-500">${patient.email}</p>
                            <p class="text-sm text-gray-500">ID: ${patient.aarogya_id}</p>
                          </div>
                          <a href="/doctor/patient/${patient.aarogya_id}" class="text-sm font-medium text-indigo-600 hover:text-indigo-500">
                            View Records
                          </a>
                        </li>
                    `;
                });
                patientHtml += '</ul>';
                patientListContainer.innerHTML = patientHtml;
            })
            .catch(error => {
                const loader = document.getElementById("patient-list-loader");
                if (loader) loader.style.display = 'none';
                patientListContainer.innerHTML = `
                  <p class="text-center text-red-500">
                    Failed to load patient list. ${error.message}
                  </p>
                `;
            });
    }

    const patientSearchForm = document.getElementById("patientSearchForm");
    const resultsContainer = document.getElementById("search-results-container");

    if (patientSearchForm) {
        patientSearchForm.addEventListener("submit", function(event) {
            event.preventDefault();
            const formData = new FormData(patientSearchForm);
            const aarogyaId = formData.get("aarogya_id");
            
            Swal.fire({
                title: 'Searching...',
                text: `Looking for patient ${aarogyaId}`,
                didOpen: () => { Swal.showLoading(); }
            });

            fetch(`/doctor/api/patients/search?aarogya_id=${aarogyaId}`)
                .then(response => {
                    if (!response.ok) { return response.json().then(err => { throw err; }); }
                    return response.json();
                })
                .then(patient => {
                    Swal.close();
                    // NEW: HTML now includes a "Send Request" button
                    resultsContainer.innerHTML = `
                        <div class="bg-white p-6 rounded-2xl shadow-md">
                            <h3 class="text-xl font-semibold text-gray-900">Patient Found</h3>
                            <div class="mt-4 space-y-2">
                                <p><strong>Name:</strong> ${patient.name.first} ${patient.name.last}</p>
                                <p><strong>Email:</strong> ${patient.email}</p>
                                <p><strong>Aarogya ID:</strong> ${patient.aarogya_id}</p>
                            </div>
                            <div class="mt-6 border-t pt-4">
                                <button id="send-connection-request"
                                        data-patient-id="${patient.aarogya_id}"
                                        class="w-full inline-flex justify-center py-2 px-4 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500">
                                    Send Connection Request
                                </button>
                            </div>
                        </div>
                    `;
                })
                .catch(error => {
                    Swal.fire({
                        icon: 'error',
                        title: 'Search Failed',
                        text: error.detail || `Could not find patient with ID ${aarogyaId}.`
                    });
                    resultsContainer.innerHTML = '';
                });
        });
    }

    // --- NEW: Add this event listener to handle the "Send Request" button click ---
    if (resultsContainer) {
        // We use event delegation to listen for clicks on the container
        resultsContainer.addEventListener('click', function(event) {
            // Check if the clicked element is our "Send Request" button
            if (event.target.id === 'send-connection-request') {
                const patientId = event.target.getAttribute('data-patient-id');
                
                Swal.fire({
                    title: 'Sending Request...',
                    text: `Sending connection request to patient ${patientId}`,
                    didOpen: () => { Swal.showLoading(); }
                });

                // Call the connection API endpoint
                fetch(`/connections/request/${patientId}`, {
                    method: 'POST'
                })
                .then(response => {
                    if (!response.ok) { return response.json().then(err => { throw err; }); }
                    return response.json();
                })
                .then(data => {
                    // Success!
                    Swal.fire({
                        icon: 'success',
                        title: 'Request Sent!',
                        text: data.message || 'The patient will be notified to accept your request.'
                    });
                    // Disable the button to prevent double-sending
                    event.target.disabled = true;
                    event.target.textContent = 'Request Sent';
                    event.target.classList.add('bg-gray-400', 'hover:bg-gray-400');
                })
                .catch(error => {
                    // Error (e.g., already connected, or request already pending)
                    Swal.fire({
                        icon: 'error',
                        title: 'Could Not Send Request',
                        text: error.detail || 'An unknown error occurred.'
                    });
                });
            }
        });
    }
    // --- NEW: Logic for Patient Dashboard Connection Requests ---
    const requestsContainer = document.getElementById("connection-requests-container");

    if (requestsContainer) {
        // 1. Fetch and display pending requests on page load
        fetch('/connections/requests/pending')
            .then(response => {
                if (!response.ok) {
                    throw new Error('Could not fetch requests.');
                }
                return response.json();
            })
            .then(requests => {
                const loader = document.getElementById("requests-loader");
                if (loader) loader.style.display = 'none';

                if (requests.length === 0) {
                    requestsContainer.innerHTML = '<p class="text-center text-gray-500">No pending connection requests.</p>';
                    return;
                }

                requests.forEach(req => {
                    const requestCard = document.createElement('div');
                    requestCard.id = `request-${req._id}`; // Use _id from schema
                    requestCard.className = 'p-4 border rounded-lg bg-gray-50 flex items-center justify-between';
                    requestCard.innerHTML = `
                        <div>
                            <p class="font-semibold text-gray-800">New Request</p>
                            <p class="text-sm text-gray-600">From: <strong>${req.doctor_email}</strong></p>
                        </div>
                        <div class="flex gap-2">
                            <button data-request-id="${req._id}" data-action="reject" class="btn-reject text-sm font-medium text-red-600 hover:text-red-800 px-3 py-1 rounded-md bg-red-100 hover:bg-red-200">
                                Reject
                            </button>
                            <button data-request-id="${req._id}" data-action="accept" class="btn-accept text-sm font-medium text-white px-3 py-1 rounded-md bg-green-600 hover:bg-green-700">
                                Accept
                            </button>
                        </div>
                    `;
                    requestsContainer.appendChild(requestCard);
                });
            })
            .catch(error => {
                const loader = document.getElementById("requests-loader");
                if (loader) loader.style.display = 'none';
                requestsContainer.innerHTML = `<p class="text-center text-red-500">${error.message}</p>`;
            });

        // 2. Use event delegation to handle button clicks
        requestsContainer.addEventListener('click', function(event) {
            const button = event.target.closest('.btn-accept, .btn-reject');
            if (!button) return;

            const requestId = button.getAttribute('data-request-id');
            const action = button.getAttribute('data-action');
            
            let url, method;

            if (action === 'accept') {
                // NOTE: Your API route for accept is a GET request
                url = `/connections/requests/accept/${requestId}`;
                method = 'GET';
            } else {
                // NOTE: Your API route for reject is a POST request
                url = `/connections/requests/reject/${requestId}`;
                method = 'POST';
            }

            Swal.fire({
                title: 'Processing...',
                text: `Please wait while we ${action} the request.`,
                didOpen: () => { Swal.showLoading(); }
            });

            fetch(url, { method: method })
                .then(response => {
                    if (!response.ok) { return response.json().then(err => { throw err; }); }
                    return response.json();
                })
                .then(data => {
                    Swal.fire({
                        icon: 'success',
                        title: 'Success!',
                        text: data.message
                    });
                    // Remove the card from the UI
                    const cardToRemove = document.getElementById(`request-${requestId}`);
                    if (cardToRemove) cardToRemove.remove();

                    // Check if any requests are left
                    if (requestsContainer.querySelectorAll('[id^="request-"]').length === 0) {
                         requestsContainer.innerHTML = '<p class="text-center text-gray-500">No pending connection requests.</p>';
                    }
                })
                .catch(error => {
                    Swal.fire({
                        icon: 'error',
                        title: 'Action Failed',
                        text: error.detail || 'An unknown error occurred.'
                    });
                });
        });
    }

    // --- NEW: Logic for Patient Reports Page ---
    const uploadForm = document.getElementById('uploadReportForm');
    const reportListContainer = document.getElementById('report-list-container');
    const structuredRecordContainer = document.getElementById('structured-record-container');

    // Helper function to fetch and display structured record
    const loadStructuredRecord = () => {
        const loader = document.getElementById('record-loader');
        if (!loader) return;

        fetch('/reports/my-structured-record')
            .then(response => response.json())
            .then(record => {
                loader.style.display = 'none';
                let html = '';

                if (record.diagnoses && record.diagnoses.length > 0) {
                    html += '<h3 class="text-md font-semibold text-gray-700">Diagnoses</h3><ul class="list-disc list-inside text-sm space-y-1">';
                    record.diagnoses.forEach(dx => {
                        html += `<li><strong>${dx.disease}</strong> (${dx.diagnosis_date ? new Date(dx.diagnosis_date).getFullYear() : 'N/A'})</li>`;
                    });
                    html += '</ul>';
                } else {
                    html += '<p class="text-sm text-gray-500">No diagnoses on record.</p>';
                }
                
                if (record.current_medications && record.current_medications.length > 0) {
                    html += '<h3 class="text-md font-semibold text-gray-700 mt-4">Medications</h3><ul class="list-disc list-inside text-sm space-y-1">';
                    record.current_medications.forEach(med => {
                        html += `<li><strong>${med.name}</strong> (${med.dosage}, ${med.frequency})</li>`;
                    });
                    html += '</ul>';
                } else {
                    html += '<p class="text-sm text-gray-500 mt-4">No medications on record.</p>';
                }

                structuredRecordContainer.innerHTML = html;
            })
            .catch(error => {
                loader.style.display = 'none';
                structuredRecordContainer.innerHTML = '<p class="text-red-500">Could not load structured record.</p>';
            });
    };

    // Helper function to fetch and display reports
    const loadReports = () => {
        const loader = document.getElementById('report-loader');
        if (!loader) return;
        
        loader.style.display = 'block';
        reportListContainer.innerHTML = ''; // Clear old list
        reportListContainer.appendChild(loader);

        fetch('/reports/my-reports')
            .then(response => response.json())
            .then(reports => {
                loader.style.display = 'none';
                if (reports.length === 0) {
                    reportListContainer.innerHTML = '<p class="text-center text-gray-500">No reports uploaded yet.</p>';
                    return;
                }

                reports.forEach(report => {
                    const reportCard = document.createElement('div');
                    reportCard.className = 'p-4 border rounded-lg bg-gray-50 flex items-center justify-between';
                    reportCard.id = `report-${report._id}`;
                    reportCard.innerHTML = `
                        <div>
                            <p class="font-semibold text-gray-800">${report.filename}</p>
                            <p class="text-sm text-gray-600">${report.report_type || 'User Upload'}</p>
                            <p class="text-xs text-gray-500">Uploaded: ${new Date(report.upload_date).toLocaleDateString()}</p>
                        </div>
                        <div class="flex gap-2" data-report-id="${report._id}">
                            <button class="btn-summarize text-sm font-medium text-indigo-600 hover:text-indigo-800" title="Get AI Summary of All Records">Summary</button>
                            <button class="btn-download text-sm font-medium text-green-600 hover:text-green-800" title="Download Report">Download</button>
                            <button class="btn-delete text-sm font-medium text-red-600 hover:text-red-800" title="Delete Report">Delete</button>
                        </div>
                    `;
                    reportListContainer.appendChild(reportCard);
                });
            })
            .catch(error => {
                loader.style.display = 'none';
                reportListContainer.innerHTML = '<p class="text-red-500">Could not load reports.</p>';
            });
    };

    // --- Main execution for Reports Page ---
    if (uploadForm && reportListContainer && structuredRecordContainer) {
        
        // 1. Load initial data
        loadStructuredRecord();
        loadReports();

        // 2. Handle file upload
        uploadForm.addEventListener('submit', function(event) {
            event.preventDefault();
            const formData = new FormData(uploadForm);

            Swal.fire({
                title: 'Uploading...',
                text: 'Please wait while your report is uploaded and processed.',
                didOpen: () => { Swal.showLoading(); }
            });

            fetch('/reports/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => {
                if (!response.ok) { return response.json().then(err => { throw err; }); }
                return response.json();
            })
            .then(data => {
                Swal.fire({
                    icon: 'success',
                    title: 'Upload Successful',
                    text: data.message || 'Your report has been uploaded.'
                });
                uploadForm.reset();
                loadReports(); // Refresh the report list
            })
            .catch(error => {
                Swal.fire({
                    icon: 'error',
                    title: 'Upload Failed',
                    text: error.detail || 'An unknown error occurred.'
                });
            });
        });

        // 3. Handle report list actions (Delete, Download, Summarize)
        reportListContainer.addEventListener('click', function(event) {
            const button = event.target;
            const reportId = button.closest('[data-report-id]').getAttribute('data-report-id');
            if (!reportId) return;

            // --- DELETE ACTION ---
            if (button.classList.contains('btn-delete')) {
                Swal.fire({
                    title: 'Are you sure?',
                    text: "You won't be able to revert this!",
                    icon: 'warning',
                    showCancelButton: true,
                    confirmButtonColor: '#d33',
                    cancelButtonColor: '#3085d6',
                    confirmButtonText: 'Yes, delete it!'
                }).then((result) => {
                    if (result.isConfirmed) {
                        fetch(`/reports/${reportId}`, { method: 'DELETE' })
                            .then(response => {
                                if (!response.ok) { throw new Error('Delete failed'); }
                                Swal.fire('Deleted!', 'Your report has been deleted.', 'success');
                                document.getElementById(`report-${reportId}`).remove(); // Remove from UI
                            })
                            .catch(error => {
                                Swal.fire('Error', 'Could not delete the report.', 'error');
                            });
                    }
                });
            }

            // --- DOWNLOAD ACTION ---
            if (button.classList.contains('btn-download')) {
                // We don't use fetch for downloads. We just point the browser to the URL.
                window.location.href = `/reports/${reportId}/download`;
            }

            // --- SUMMARY ACTION ---
            if (button.classList.contains('btn-summarize')) {
                Swal.fire({
                    title: 'Generating Summary...',
                    text: 'The AI is reading your full medical record to provide a summary.',
                    didOpen: () => { Swal.showLoading(); }
                });
                
                fetch(`/reports/${reportId}/summarize`, { method: 'POST' })
                    .then(response => {
                        if (!response.ok) { return response.json().then(err => { throw err; }); }
                        return response.json();
                    })
                    .then(data => {
                        Swal.fire({
                            title: 'AI Medical Summary',
                            // Use text-align: left for readable medical text
                            html: `<div style="text-align: left; white-space: pre-wrap; padding: 1em;">${data.summary}</div>`,
                            icon: 'info',
                            width: '800px'
                        });
                    })
                    .catch(error => {
                        Swal.fire('Error', error.detail || 'Could not generate summary.', 'error');
                    });
            }
        });
    }
    // --- NEW: Logic for Doctor's Patient Record View Page ---
    const docPatientReportContainer = document.getElementById('doctor-patient-report-list');
    if (docPatientReportContainer) {
        const patientId = docPatientReportContainer.getAttribute('data-patient-id');
        const loader = document.getElementById('doc-report-loader');

        // We call the NEW API route we created in Step 1
        fetch(`/reports/patient-by-id/${patientId}`)
            .then(response => {
                if (!response.ok) { return response.json().then(err => { throw err; }); }
                return response.json();
            })
            .then(reports => {
                loader.style.display = 'none';
                if (reports.length === 0) {
                    docPatientReportContainer.innerHTML = '<p class="text-center text-gray-500">No reports found for this patient.</p>';
                    return;
                }

                reports.forEach(report => {
                    const reportCard = document.createElement('div');
                    reportCard.className = 'p-4 border rounded-lg bg-gray-50 flex items-center justify-between';
                    reportCard.innerHTML = `
                        <div>
                            <p class="font-semibold text-gray-800">${report.filename}</p>
                            <p class="text-sm text-gray-600">${report.report_type || 'Patient Upload'}</p>
                            <p class="text-xs text-gray-500">Uploaded: ${new Date(report.upload_date).toLocaleDateString()}</p>
                        </div>
                        <div class="flex gap-2" data-report-id="${report._id}">
                            <button class="btn-doc-summarize text-sm font-medium text-indigo-600 hover:text-indigo-800">Summary</button>
                            <button class="btn-doc-download text-sm font-medium text-green-600 hover:text-green-800">Download</button>
                        </div>
                    `;
                    docPatientReportContainer.appendChild(reportCard);
                });
            })
            .catch(error => {
                loader.style.display = 'none';
                docPatientReportContainer.innerHTML = `<p class="text-center text-red-500">Error: ${error.detail || 'Could not load reports.'}</p>`;
            });

            docPatientReportContainer.addEventListener('click', function(event) {
            const button = event.target;
            // Find the parent div with the report ID
            const reportId = button.closest('[data-report-id]')?.getAttribute('data-report-id');
            if (!reportId) return;

            // --- DOWNLOAD ACTION (Doctor) ---
            if (button.classList.contains('btn-doc-download')) {
                // Call the new doctor-specific download route
                window.location.href = `/reports/doctor/download/${reportId}`;
            }

            // --- SUMMARY ACTION (Doctor) ---
            if (button.classList.contains('btn-doc-summarize')) {
                Swal.fire({
                    title: 'Generating Summary...',
                    text: "The AI is reading the patient's full medical record.",
                    didOpen: () => { Swal.showLoading(); }
                });
                
                // Call the new doctor-specific summarize route
                fetch(`/reports/doctor/summarize/${reportId}`, { method: 'POST' })
                    .then(response => {
                        if (!response.ok) { return response.json().then(err => { throw err; }); }
                        return response.json();
                    })
                    .then(data => {
                        Swal.fire({
                            title: 'AI Medical Summary',
                            html: `<div style="text-align: left; white-space: pre-wrap; padding: 1em;">${data.summary}</div>`,
                            icon: 'info',
                            width: '800px'
                        });
                    })
                    .catch(error => {
                        Swal.fire('Error', error.detail || 'Could not generate summary.', 'error');
                    });
            }
        });
        
        // Also load the patient's details for the header/info box
        const patientDetailsContainer = document.getElementById('patient-details-container');
        const patientHeader = document.getElementById('patient-details-header');
        
        // We can reuse the patient search API for this
        fetch(`/doctor/api/patients/search?aarogya_id=${patientId}`)
            .then(response => response.json())
            .then(patient => {
                patientHeader.textContent = `Viewing Records for: ${patient.name.first} ${patient.name.last}`;
                patientDetailsContainer.innerHTML = `
                    <p><strong>Name:</strong> ${patient.name.first} ${patient.name.last}</p>
                    <p><strong>Email:</strong> ${patient.email}</p>
                    <p><strong>Aarogya ID:</strong> ${patient.aarogya_id}</p>
                `;
            })
            .catch(err => {
                patientDetailsContainer.innerHTML = '<p class="text-red-500">Could not load patient details.</p>';
            });
    }

    // --- NEW: Logic for Appointments Page ---
    // --- NEW: Logic for Appointments Page ---
    const patientAppointmentsView = document.getElementById('patient-appointments-view');
    const doctorAppointmentsView = document.getElementById('doctor-appointments-view');

    // --- 1. If this is the PATIENT'S view ---
    if (patientAppointmentsView) {
        const doctorSelect = document.getElementById('doctor-select');
        const requestForm = document.getElementById('requestAppointmentForm');

        // Load connected doctors into the dropdown
        fetch('/appointments/doctors/connected') // Corrected URL with prefix
            .then(response => {
                if (!response.ok) throw new Error('Could not fetch doctors.');
                return response.json();
            })
            .then(doctors => {
                if (doctors.length === 0) {
                    doctorSelect.innerHTML = '<option value="" disabled>No connected doctors found.</option>';
                    return;
                }
                doctorSelect.innerHTML = '<option value="" disabled selected>Select a doctor</option>';
                doctors.forEach(doc => {
                    const option = document.createElement('option');
                    option.value = doc.aarogya_id;
                    option.textContent = `Dr. ${doc.email} (ID: ${doc.aarogya_id})`;
                    doctorSelect.appendChild(option);
                });
            })
            .catch(err => {
                doctorSelect.innerHTML = '<option value="" disabled>Error loading doctors.</option>';
            });

        // Handle the appointment request form submission
        requestForm.addEventListener('submit', function(event) {
            event.preventDefault();
            const formData = new FormData(requestForm);
            const body = new URLSearchParams(formData); // Send as form data

            Swal.fire({
                title: 'Sending Request...',
                text: 'Please wait.',
                didOpen: () => { Swal.showLoading(); }
            });

            fetch('/appointments/request', { // Corrected backend to accept form data
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: body
            })
            .then(response => {
                if (!response.ok) { return response.json().then(err => { throw err; }); }
                return response.json();
            })
            .then(data => {
                Swal.fire({
                    icon: 'success',
                    title: 'Request Sent!',
                    text: data.message || 'Your request has been sent to the doctor.'
                });
                requestForm.reset();
            })
            .catch(error => {
                Swal.fire({
                    icon: 'error',
                    title: 'Oops...',
                    text: error.detail || 'Could not send request. Do you have a pending request with this doctor?'
                });
            });
        });
    }

    // --- 2. If this is the DOCTOR'S view ---
    if (doctorAppointmentsView) {
        const container = document.getElementById('pending-requests-container');
        const loader = document.getElementById('pending-loader');

        // Load pending requests for the doctor
        fetch('/appointments/pending') // Correct URL
            .then(response => {
                if (!response.ok) throw new Error('Could not fetch requests.');
                return response.json();
            })
            .then(requests => {
                loader.style.display = 'none';
                if (requests.length === 0) {
                    container.innerHTML = '<p class="text-center text-gray-500">No pending appointment requests.</p>';
                    return;
                }

                requests.forEach(req => {
                    const card = document.createElement('div');
                    card.className = 'bg-white p-6 rounded-2xl shadow-md space-y-4';
                    card.id = `request-card-${req._id}`; // Use _id from schema

                    // Apply color based on severity
                    let severityClass = 'bg-gray-100 text-gray-800';
                    if (req.predicted_severity === 'Very Serious') {
                        severityClass = 'bg-red-100 text-red-800';
                    } else if (req.predicted_severity === 'Moderate') {
                        severityClass = 'bg-yellow-100 text-yellow-800';
                    }

                    // This is the updated HTML with the Reject button
                    card.innerHTML = `
                        <div class="flex justify-between items-center">
                            <h3 class="text-lg font-semibold text-gray-900">Patient: ${req.patient_email}</h3>
                            <span class="inline-flex items-center px-3 py-0.5 rounded-full text-sm font-medium ${severityClass}">
                                ${req.predicted_severity || 'N/A'}
                            </span>
                        </div>
                        <p class="text-sm text-gray-700"><strong>Reason:</strong> ${req.reason}</p>
                        <p class="text-sm text-gray-600"><strong>Symptoms/Notes:</strong> ${req.patient_notes || 'No notes provided.'}</p>
                        
                        <div class="border-t pt-4 space-y-2">
                            <label for="time-${req._id}" class="block text-sm font-medium text-gray-700">Set Appointment Time:</label>
                            <input type="datetime-local" id="time-${req._id}" name="appointment_time" 
                                   class="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm">
                            <button data-request-id="${req._id}" 
                                    class="btn-confirm-appointment w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500">
                                Confirm Appointment
                            </button>
                            <button data-request-id="${req._id}" 
                                    class="btn-reject-appointment w-full flex justify-center py-2 px-4 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 mt-2">
                                Reject
                            </button>
                        </div>
                    `;
                    container.appendChild(card);
                });
            })
            .catch(err => {
                loader.style.display = 'none';
                container.innerHTML = `<p class="text-center text-red-500">Error: ${err.message}</p>`;
            });

        // --- THIS IS THE COMBINED EVENT LISTENER ---
        // Use event delegation to handle button clicks
        container.addEventListener('click', function(event) {
            // Find the button that was clicked
            const button = event.target.closest('.btn-confirm-appointment, .btn-reject-appointment');
            
            // If the click wasn't on one of our buttons, do nothing
            if (!button) return; 

            const requestId = button.getAttribute('data-request-id');

            // --- IF: CONFIRM ACTION ---
            if (button.classList.contains('btn-confirm-appointment')) {
                const timeInput = document.getElementById(`time-${requestId}`);
                const appointmentTime = timeInput.value;

                if (!appointmentTime) {
                    Swal.fire('Error', 'Please select a date and time for the appointment.', 'error');
                    return;
                }

                Swal.fire({
                    title: 'Confirming...',
                    text: 'Please wait.',
                    didOpen: () => { Swal.showLoading(); }
                });

                fetch('/appointments/confirm', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        request_id: requestId,
                        appointment_time: appointmentTime
                    })
                })
                .then(response => {
                    if (!response.ok) { return response.json().then(err => { throw err; }); }
                    return response.json();
                })
                .then(data => {
                    Swal.fire({
                        icon: 'success',
                        title: 'Confirmed!',
                        text: data.message
                    });
                    document.getElementById(`request-card-${requestId}`).remove();
                    if (container.children.length === 0) {
                         container.innerHTML = '<p class="text-center text-gray-500">No pending appointment requests.</p>';
                    }
                })
                .catch(error => {
                    Swal.fire({
                        icon: 'error',
                        title: 'Failed to Confirm',
                        text: error.detail || 'An unknown error occurred.'
                    });
                });
            }
            
            // --- ELSE IF: REJECT ACTION ---
            else if (button.classList.contains('btn-reject-appointment')) {
                Swal.fire({
                    title: 'Are you sure?',
                    text: "Do you want to reject this appointment request?",
                    icon: 'warning',
                    showCancelButton: true,
                    confirmButtonColor: '#d33',
                    cancelButtonColor: '#3085d6',
                    confirmButtonText: 'Yes, reject it!'
                }).then((result) => {
                    if (result.isConfirmed) {
                        fetch('/appointments/reject', { // Calls the new reject route
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ request_id: requestId })
                        })
                        .then(response => {
                            if (!response.ok) { return response.json().then(err => { throw err; }); }
                            return response.json();
                        })
                        .then(data => {
                            Swal.fire('Rejected!', data.message, 'success');
                            document.getElementById(`request-card-${requestId}`).remove();
                            if (container.children.length === 0) {
                                container.innerHTML = '<p class="text-center text-gray-500">No pending appointment requests.</p>';
                            }
                        })
                        .catch(error => {
                            Swal.fire('Failed', error.detail || 'Could not reject.', 'error');
                        });
                    }
                });
            }
        });
    }
});