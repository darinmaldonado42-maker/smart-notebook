const tg = window.Telegram.WebApp;
let notesList = [];
let currentCategory = "all";
let searchQuery = "";

// Initialize Telegram WebApp
tg.ready();
tg.expand();

// Adapt background colors from Telegram theme variables
try {
    tg.setHeaderColor('secondary_bg_color');
    tg.setBackgroundColor('bg_color');
} catch (e) {
    console.error("Failed to set colors via Telegram SDK:", e);
}

// Cross-platform helpers: use native Telegram popups ONLY when running inside Telegram (tg.initData is non-empty).
// In a regular browser tg.showConfirm/showAlert exist but never fire their callbacks — so we fall back to browser APIs.
function showAlert(msg) {
    if (tg.initData) {
        tg.showAlert(msg);
    } else {
        alert(msg);
    }
}

function showConfirm(msg, callback) {
    if (tg.initData) {
        tg.showConfirm(msg, callback);
    } else {
        const result = window.confirm(msg);
        callback(result);
    }
}

// User details setup - read from Telegram SDK, or fall back to URL query param for local dev
const urlParams = new URLSearchParams(window.location.search);
const urlUserId = urlParams.get("user_id");
const tgUser = tg.initDataUnsafe?.user;

const user = tgUser || {
    id: urlUserId ? parseInt(urlUserId) : 0,
    first_name: "Разработчик"
};

document.getElementById("user-name").innerText = user.first_name || "Пользователь";

// Set user avatar character if available
if (user.first_name) {
    document.getElementById("user-avatar").innerText = user.first_name.charAt(0);
}

// DOM references
const notesGrid = document.getElementById("notes-grid");
const loadingState = document.getElementById("loading-state");
const emptyState = document.getElementById("empty-state");
const searchInput = document.getElementById("search-input");
const searchClear = document.getElementById("search-clear");
const refreshBtn = document.getElementById("refresh-btn");

// Helper to determine category class names
function getCategoryClass(category) {
    switch (category) {
        case "Идея": return "idea";
        case "Задача": return "task";
        case "Учеба": return "study";
        case "Повседневное": return "daily";
        default: return "daily";
    }
}

// Loader UI toggle
function showLoading(isLoading) {
    if (isLoading) {
        loadingState.classList.remove("hidden");
        notesGrid.classList.add("hidden");
        emptyState.classList.add("hidden");
    } else {
        loadingState.classList.add("hidden");
    }
}

// Request headers generator
function getHeaders() {
    const headers = {
        "Content-Type": "application/json",
        "Bypass-Tunnel-Reminder": "true"   // bypass localtunnel landing page
    };
    if (tg.initData) {
        headers["Authorization"] = `tma ${tg.initData}`;
    }
    return headers;
}

// Fetch notes from DB
async function loadNotes() {
    showLoading(true);
    try {
        const base = window.API_BASE || "";
        const queryParams = tg.initData ? "" : `?user_id=${user.id}`;
        const response = await fetch(`${base}/api/notes${queryParams}`, {
            headers: getHeaders()
        });
        
        if (!response.ok) {
            throw new Error(`Ошибка HTTP: ${response.status}`);
        }
        
        const data = await response.json();
        notesList = data.notes || [];
        renderNotes();
    } catch (e) {
        console.error("Error loading notes:", e);
        notesGrid.innerHTML = `
            <div class="center-state">
                <i class="fa-solid fa-triangle-exclamation" style="font-size: 28px; color: var(--accent-daily);"></i>
                <h3>Не удалось загрузить данные</h3>
                <p>${e.message || "Пожалуйста, проверьте подключение к интернету."}</p>
            </div>
        `;
        notesGrid.classList.remove("hidden");
    } finally {
        showLoading(false);
    }
}

// Delete note action
async function deleteNote(noteId, cardElement) {
    showConfirm("Вы действительно хотите окончательно удалить эту заметку?", async (confirmed) => {
        if (!confirmed) return;
        
        try {
            const base = window.API_BASE || "";
            const queryParams = tg.initData ? "" : `?user_id=${user.id}`;
            const response = await fetch(`${base}/api/notes/${noteId}${queryParams}`, {
                method: "DELETE",
                headers: getHeaders()
            });
            
            if (!response.ok) {
                throw new Error("Не удалось удалить запись на сервере");
            }
            
            // Bouncy removal animation
            cardElement.classList.add("fade-out");
            setTimeout(() => {
                notesList = notesList.filter(note => note.id !== noteId);
                renderNotes();
            }, 300);
            
            if (tg.HapticFeedback) {
                tg.HapticFeedback.notificationOccurred("success");
            }
        } catch (e) {
            showAlert(`Ошибка при удалении: ${e.message}`);
        }
    });
}

// Render list dynamically
function renderNotes() {
    let filtered = notesList;
    
    // 1. Filter by category
    if (currentCategory !== "all") {
        filtered = filtered.filter(note => note.category === currentCategory);
    }
    
    // 2. Filter by search input
    if (searchQuery) {
        const query = searchQuery.toLowerCase();
        filtered = filtered.filter(note => 
            note.summary.toLowerCase().includes(query) ||
            note.original_text.toLowerCase().includes(query) ||
            note.tasks.some(task => task.toLowerCase().includes(query))
        );
    }

    // Handle empty results
    if (filtered.length === 0) {
        notesGrid.classList.add("hidden");
        emptyState.classList.remove("hidden");
        return;
    }

    emptyState.classList.add("hidden");
    notesGrid.classList.remove("hidden");
    notesGrid.innerHTML = "";

    filtered.forEach(note => {
        const dateObj = new Date(note.created_at);
        const dateStr = dateObj.toLocaleDateString("ru-RU", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit"
        });

        // Card container
        const card = document.createElement("div");
        card.className = `note-card cat-${getCategoryClass(note.category)}`;
        card.dataset.id = note.id;

        // Card header
        const cardHeader = document.createElement("div");
        cardHeader.className = "note-header";
        
        const noteMeta = document.createElement("div");
        noteMeta.className = "note-meta";
        noteMeta.innerHTML = `<span class="category-tag">${note.category}</span> <span class="note-date">${dateStr}</span>`;
        cardHeader.appendChild(noteMeta);

        // Actions buttons container
        const noteActions = document.createElement("div");
        noteActions.className = "note-actions";
        
        // Share action button
        const shareBtn = document.createElement("button");
        shareBtn.className = "action-btn share";
        shareBtn.innerHTML = `<i class="fa-solid fa-share-nodes"></i>`;
        shareBtn.title = "Поделиться";
        shareBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            const taskBullets = note.tasks.length ? note.tasks.map(t => `• ${t}`).join("\n") : "Задачи отсутствуют.";
            const shareText = `📂 Категория: #${note.category}\n🎯 Главное:\n${note.summary}\n\n📝 Задачи:\n${taskBullets}\n\n🎙️ Оригинал мыслей:\n${note.original_text}`;
            
            navigator.clipboard.writeText(shareText).then(() => {
                showAlert("Текст заметки скопирован в буфер обмена!");
                if (tg.HapticFeedback) tg.HapticFeedback.impactOccurred("medium");
            }).catch(() => {
                showAlert("Не удалось скопировать текст в буфер обмена.");
            });
        });
        noteActions.appendChild(shareBtn);

        // Delete action button
        const deleteBtn = document.createElement("button");
        deleteBtn.className = "action-btn delete";
        deleteBtn.innerHTML = `<i class="fa-solid fa-trash-can"></i>`;
        deleteBtn.title = "Удалить";
        deleteBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            deleteNote(note.id, card);
        });
        noteActions.appendChild(deleteBtn);
        cardHeader.appendChild(noteActions);
        card.appendChild(cardHeader);

        // Title (main heading)
        const titleEl = document.createElement("div");
        titleEl.className = "note-title";
        titleEl.innerText = note.title || "Без названия";
        card.appendChild(titleEl);

        // Summary (subtitle below title)
        const summary = document.createElement("div");
        summary.className = "note-summary";
        summary.innerText = note.summary;
        card.appendChild(summary);

        // Expandable details container
        const details = document.createElement("div");
        details.className = "note-details hidden";

        // Checklist tasks
        if (note.tasks && note.tasks.length > 0) {
            const tasksTitle = document.createElement("div");
            tasksTitle.className = "tasks-title";
            tasksTitle.innerHTML = `<i class="fa-solid fa-circle-check"></i> Выжимка задач`;
            details.appendChild(tasksTitle);

            const taskList = document.createElement("div");
            taskList.className = "task-list";
            
            note.tasks.forEach((task, index) => {
                const taskItem = document.createElement("button");
                taskItem.className = "task-item";
                taskItem.style.background = "transparent";
                taskItem.style.border = "none";
                taskItem.style.width = "100%";
                taskItem.style.textAlign = "left";
                
                const taskKey = `note_${note.id}_task_${index}`;
                const isCompleted = localStorage.getItem(taskKey) === "true";
                if (isCompleted) {
                    taskItem.classList.add("checked");
                }

                taskItem.innerHTML = `
                    <div class="task-checkbox"><i class="fa-solid fa-check"></i></div>
                    <span class="task-text">${task}</span>
                `;

                taskItem.addEventListener("click", (evt) => {
                    evt.stopPropagation();
                    const state = taskItem.classList.toggle("checked");
                    localStorage.setItem(taskKey, state ? "true" : "false");
                    
                    if (tg.HapticFeedback) {
                        tg.HapticFeedback.impactOccurred("light");
                    }
                });

                taskList.appendChild(taskItem);
            });
            details.appendChild(taskList);
        }

        // Original Speech Transcript section
        const originalSection = document.createElement("div");
        originalSection.className = "original-section";
        originalSection.innerHTML = `
            <div class="original-title"><i class="fa-solid fa-quote-left"></i> Оригинальная речь</div>
            <div class="original-text-content">${note.original_text}</div>
        `;
        details.appendChild(originalSection);
        details.style.cursor = "default";
        // Stop detail click propagation to prevent card auto-closing on text copying
        details.addEventListener("click", (evt) => evt.stopPropagation());
        
        card.appendChild(details);

        // Expand Chevron indicator
        const expandIndicator = document.createElement("div");
        expandIndicator.className = "expand-indicator";
        expandIndicator.innerHTML = `<span class="expand-txt">Развернуть</span> <i class="fa-solid fa-chevron-down"></i>`;
        card.appendChild(expandIndicator);

        // Expand/Collapse click logic
        card.addEventListener("click", () => {
            const isClosed = details.classList.toggle("hidden");
            if (isClosed) {
                expandIndicator.querySelector(".expand-txt").innerText = "Развернуть";
                expandIndicator.querySelector("i").className = "fa-solid fa-chevron-down";
            } else {
                expandIndicator.querySelector(".expand-txt").innerText = "Свернуть";
                expandIndicator.querySelector("i").className = "fa-solid fa-chevron-up";
            }
            if (tg.HapticFeedback) {
                tg.HapticFeedback.impactOccurred("light");
            }
        });

        notesGrid.appendChild(card);
    });
}

// Search interaction
searchInput.addEventListener("input", (e) => {
    searchQuery = e.target.value;
    if (searchQuery.length > 0) {
        searchClear.classList.remove("hidden");
    } else {
        searchClear.classList.add("hidden");
    }
    renderNotes();
});

searchClear.addEventListener("click", () => {
    searchInput.value = "";
    searchQuery = "";
    searchClear.classList.add("hidden");
    renderNotes();
});

// Category pills interaction
const capsules = document.querySelectorAll(".filter-capsule");
capsules.forEach(capsule => {
    capsule.addEventListener("click", () => {
        capsules.forEach(c => c.classList.remove("active"));
        capsule.classList.add("active");
        currentCategory = capsule.dataset.category;
        renderNotes();
        
        if (tg.HapticFeedback) {
            tg.HapticFeedback.impactOccurred("light");
        }
    });
});

// Refresh button interaction
refreshBtn.addEventListener("click", () => {
    loadNotes();
    if (tg.HapticFeedback) {
        tg.HapticFeedback.impactOccurred("medium");
    }
});

// Initial boot
loadNotes();
