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

// Set user avatar securely from the Telegram Proxy API, fallback to letter initial
const avatarEl = document.getElementById("user-avatar");
if (user.id) {
    avatarEl.innerHTML = `<img src="${window.API_BASE || ''}/api/avatar?user_id=${user.id}" alt="" onerror="fallbackAvatar()">`;
} else {
    fallbackAvatar();
}

function fallbackAvatar() {
    avatarEl.innerHTML = user.first_name ? user.first_name.charAt(0) : "👤";
}

// DOM references
const notesGrid = document.getElementById("notes-grid");
const loadingState = document.getElementById("loading-state");
const emptyState = document.getElementById("empty-state");
const searchInput = document.getElementById("search-input");
const searchClear = document.getElementById("search-clear");
const refreshBtn = document.getElementById("refresh-btn");

// Helper to determine category class names
let categoriesList = [];

// Helper to determine category color theme
function getNoteCategoryColor(categoryName) {
    const cat = categoriesList.find(c => c.name === categoryName);
    return cat ? cat.color : "study"; // fallback to blue/study
}

function getDefaultIconForColor(color) {
    switch (color) {
        case "idea": return "lightbulb";
        case "study": return "graduation-cap";
        case "task": return "list-check";
        case "daily": return "house";
        case "work": return "briefcase";
        case "finance": return "wallet";
        case "health": return "heart-pulse";
        case "shopping": return "cart-shopping";
        case "creative": return "palette";
        case "travel": return "plane";
        default: return "tag";
    }
}

function getCategoryIcon(cat) {
    if (cat.icon && cat.icon !== "tag") {
        return cat.icon;
    }
    return getDefaultIconForColor(cat.color);
}

function getNoteCategoryIcon(categoryName) {
    const cat = categoriesList.find(c => c.name === categoryName);
    return cat ? getCategoryIcon(cat) : "tag"; // fallback to tag icon
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

// Fetch categories from API
async function loadCategories() {
    try {
        const base = window.API_BASE || "";
        const queryParams = tg.initData ? "" : `?user_id=${user.id}`;
        const response = await fetch(`${base}/api/categories${queryParams}`, {
            headers: getHeaders()
        });
        if (response.ok) {
            const data = await response.json();
            categoriesList = data.categories || [];
            renderCategoriesUI();
        }
    } catch (e) {
        console.error("Error loading categories:", e);
    }
}

// Dynamically render filter capsules
const filtersContainer = document.getElementById("filters-container");
function renderCategoriesUI() {
    if (!filtersContainer) return;
    filtersContainer.innerHTML = "";
    
    // 1. "Все" filter button
    const allBtn = document.createElement("button");
    allBtn.className = `filter-capsule ${currentCategory === 'all' ? 'active' : ''}`;
    allBtn.dataset.category = "all";
    allBtn.innerText = "Все";
    allBtn.addEventListener("click", () => selectCategory("all", allBtn));
    filtersContainer.appendChild(allBtn);
    
    // 2. Custom category buttons
    categoriesList.forEach(cat => {
        const btn = document.createElement("button");
        btn.className = `filter-capsule ${currentCategory === cat.name ? 'active' : ''}`;
        btn.dataset.category = cat.name;
        
        btn.innerHTML = `<i class="fa-solid fa-${getCategoryIcon(cat)}"></i> ${cat.name}`;
        btn.addEventListener("click", () => selectCategory(cat.name, btn));
        filtersContainer.appendChild(btn);
    });
}

function selectCategory(catName, btnElement) {
    document.querySelectorAll(".filter-capsule").forEach(c => c.classList.remove("active"));
    btnElement.classList.add("active");
    currentCategory = catName;
    renderNotes();
    if (tg.HapticFeedback) tg.HapticFeedback.impactOccurred("light");
}

// Modal category manager
const modal = document.getElementById("categories-modal");
const closeModalBtn = document.getElementById("close-modal-btn");
const categoryManagerList = document.getElementById("category-manager-list");
const addCategoryForm = document.getElementById("add-category-form");
const newCatNameInput = document.getElementById("new-category-name");
const addCatBtn = document.getElementById("add-cat-btn");

let selectedColor = "idea";
let selectedIcon = "lightbulb";

// Setup color option clicks in modal
document.querySelectorAll(".color-option").forEach(opt => {
    opt.addEventListener("click", () => {
        document.querySelectorAll(".color-option").forEach(o => o.classList.remove("selected"));
        opt.classList.add("selected");
        selectedColor = opt.dataset.color;
    });
});

// Setup icon option clicks in modal
document.querySelectorAll(".icon-option").forEach(opt => {
    opt.addEventListener("click", () => {
        document.querySelectorAll(".icon-option").forEach(o => o.classList.remove("selected"));
        opt.classList.add("selected");
        selectedIcon = opt.dataset.icon;
    });
});

if (addCatBtn) {
    addCatBtn.addEventListener("click", () => openCategoriesModal());
}

function openCategoriesModal() {
    modal.classList.add("active");
    renderCategoryManagerList();
}

function closeCategoriesModal() {
    modal.classList.remove("active");
}

if (closeModalBtn) {
    closeModalBtn.addEventListener("click", closeCategoriesModal);
}

function renderCategoryManagerList() {
    if (!categoryManagerList) return;
    categoryManagerList.innerHTML = "";
    categoriesList.forEach(cat => {
        const item = document.createElement("div");
        item.className = "category-manager-item";
        item.innerHTML = `
            <div class="category-item-label">
                <span class="category-icon-preview ${cat.color}" style="color: var(--accent-${cat.color}); font-size: 14px; width: 20px; text-align: center; margin-right: 4px;">
                    <i class="fa-solid fa-${getCategoryIcon(cat)}"></i>
                </span>
                <span>${cat.name}</span>
            </div>
            <button class="delete-cat-btn" data-id="${cat.id}"><i class="fa-solid fa-trash-can"></i></button>
        `;
        item.querySelector(".delete-cat-btn").addEventListener("click", () => deleteCategory(cat.id));
        categoryManagerList.appendChild(item);
    });
}

async function deleteCategory(id) {
    showConfirm("Удалить эту категорию? Заметки в ней останутся, но ИИ больше не будет относить новые задачи к этой категории.", async (confirmed) => {
        if (!confirmed) return;
        try {
            const base = window.API_BASE || "";
            const queryParams = tg.initData ? "" : `?user_id=${user.id}`;
            const response = await fetch(`${base}/api/categories/${id}${queryParams}`, {
                method: "DELETE",
                headers: getHeaders()
            });
            if (response.ok) {
                categoriesList = categoriesList.filter(c => c.id !== id);
                renderCategoryManagerList();
                renderCategoriesUI();
                renderNotes();
                if (tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
            } else {
                showAlert("Не удалось удалить категорию.");
            }
        } catch (e) {
            console.error("Error deleting category:", e);
        }
    });
}

if (addCategoryForm) {
    addCategoryForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const name = newCatNameInput.value.trim();
        if (!name) return;
        
        if (categoriesList.some(c => c.name.toLowerCase() === name.toLowerCase())) {
            showAlert("Категория с таким именем уже существует!");
            return;
        }
        
        try {
            const base = window.API_BASE || "";
            const queryParams = tg.initData ? "" : `?user_id=${user.id}`;
            const response = await fetch(`${base}/api/categories${queryParams}`, {
                method: "POST",
                headers: getHeaders(),
                body: JSON.stringify({ name, color: selectedColor, icon: selectedIcon })
            });
            if (response.ok) {
                const newCat = await response.json();
                categoriesList.push(newCat);
                newCatNameInput.value = "";
                renderCategoryManagerList();
                renderCategoriesUI();
                if (tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
            } else {
                showAlert("Не удалось добавить категорию.");
            }
        } catch (err) {
            console.error("Error creating category:", err);
        }
    });
}

// Fetch notes from DB
async function loadNotes() {
    showLoading(true);
    try {
        await loadCategories(); // Load custom categories first for mapping
        
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
        card.className = `note-card cat-color-${getNoteCategoryColor(note.category)}`;
        card.dataset.id = note.id;

        // Card header
        const cardHeader = document.createElement("div");
        cardHeader.className = "note-header";
        
        const noteMeta = document.createElement("div");
        noteMeta.className = "note-meta";
        noteMeta.innerHTML = `<span class="category-tag"><i class="fa-solid fa-${getNoteCategoryIcon(note.category)}"></i> ${note.category}</span> <span class="note-date">${dateStr}</span>`;
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
            const taskBullets = note.tasks.length ? note.tasks.map(t => `• ${typeof t === 'string' ? t : t.text}`).join("\n") : "Задачи отсутствуют.";
            const shareText = `📂 Категория: #${note.category}\n🎯 Главное:\n${note.summary}\n\n📝 Задачи:\n${taskBullets}\n\n🎙️ Оригинал мыслей:\n${note.original_text}`;
            
            navigator.clipboard.writeText(shareText).then(() => {
                showAlert("Текст заметки скопирован в буфер обмена!");
                if (tg.HapticFeedback) tg.HapticFeedback.impactOccurred("medium");
            }).catch(() => {
                showAlert("Не удалось скопировать текст в буфер обмена.");
            });
        });
        noteActions.appendChild(shareBtn);

        // Edit action button
        const editBtn = document.createElement("button");
        editBtn.className = "action-btn edit";
        editBtn.innerHTML = `<i class="fa-solid fa-pen"></i>`;
        editBtn.title = "Редактировать";
        editBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            openEditorForEdit(note);
        });
        noteActions.appendChild(editBtn);

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

        // Checklist tasks (always visible, directly under title)
        if (note.tasks && note.tasks.length > 0) {
            const taskList = document.createElement("div");
            taskList.className = "task-list";
            taskList.style.marginTop = "8px";
            taskList.style.marginBottom = "4px";
            
            note.tasks.forEach((task, index) => {
                const taskItem = document.createElement("button");
                taskItem.className = "task-item";
                taskItem.style.background = "transparent";
                taskItem.style.border = "none";
                taskItem.style.width = "100%";
                taskItem.style.textAlign = "left";
                
                const taskText = typeof task === "string" ? task : task.text;
                const taskKey = `note_${note.id}_task_${index}`;
                // Fallback to localStorage check if boolean field not defined (e.g. legacy notes)
                const isCompleted = typeof task === "string" 
                    ? (localStorage.getItem(taskKey) === "true") 
                    : task.completed;
                
                if (isCompleted) {
                    taskItem.classList.add("checked");
                }

                taskItem.innerHTML = `
                    <div class="task-checkbox"><i class="fa-solid fa-check"></i></div>
                    <span class="task-text">${taskText}</span>
                `;

                taskItem.addEventListener("click", async (evt) => {
                    evt.stopPropagation(); // prevent card expand toggle when checking a task
                    const wasChecked = taskItem.classList.contains("checked");
                    const isCheckedNow = !wasChecked;
                    taskItem.classList.toggle("checked", isCheckedNow);
                    
                    // Update object in memory
                    if (typeof task === "string") {
                        note.tasks[index] = { text: task, completed: isCheckedNow };
                    } else {
                        note.tasks[index].completed = isCheckedNow;
                    }
                    localStorage.setItem(taskKey, isCheckedNow ? "true" : "false");
                    
                    // Sync to DB
                    try {
                        const base = window.API_BASE || "";
                        const queryParams = tg.initData ? "" : `?user_id=${user.id}`;
                        await fetch(`${base}/api/notes/${note.id}${queryParams}`, {
                            method: "PUT",
                            headers: getHeaders(),
                            body: JSON.stringify({ tasks: note.tasks })
                        });
                    } catch (e) {
                        console.error("Failed to sync checklist checkbox to DB:", e);
                    }
                    
                    if (tg.HapticFeedback) {
                        tg.HapticFeedback.impactOccurred("light");
                    }
                });

                taskList.appendChild(taskItem);
            });
            card.appendChild(taskList);
        }

        // Expandable details container (hidden initially)
        const details = document.createElement("div");
        details.className = "note-details hidden";

        // Summary section (inside details container, hidden initially)
        const summarySection = document.createElement("div");
        summarySection.className = "summary-section";
        summarySection.style.marginBottom = "12px";
        summarySection.innerHTML = `
            <div class="summary-title" style="font-family: var(--font-title); font-size: 12px; font-weight: 600; color: var(--theme-color); text-transform: uppercase; letter-spacing: 0.3px; display: flex; align-items: center; gap: 6px; margin-bottom: 6px;"><i class="fa-solid fa-lightbulb"></i> Суть заметки</div>
            <div class="summary-text" style="font-size: 13.5px; color: var(--text-color); line-height: 1.45; background: rgba(255, 255, 255, 0.02); padding: 10px 12px; border-radius: 10px; border-left: 3px solid var(--theme-color);">${note.summary}</div>
        `;
        details.appendChild(summarySection);

        // Original Speech Transcript section (inside details container, hidden initially)
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



// Note Editor Modal elements
const editorModal = document.getElementById("note-editor-modal");
const closeEditorBtn = document.getElementById("close-editor-btn");
const noteEditorForm = document.getElementById("note-editor-form");
const editorTitle = document.getElementById("editor-note-title");
const editorSummary = document.getElementById("editor-note-summary");
const editorCategory = document.getElementById("editor-note-category");
const editorReminder = document.getElementById("editor-note-reminder");
const editorTasksList = document.getElementById("editor-tasks-list");
const editorAddTaskBtn = document.getElementById("editor-add-task-btn");
const createNoteBtn = document.getElementById("create-note-btn");
const editorModalTitleLabel = document.getElementById("note-editor-title");

let editorMode = "create"; // "create" or "edit"
let editingNoteId = null;

// Populate category options in select element
function populateEditorCategoryOptions(selectedCategoryName = "") {
    if (!editorCategory) return;
    editorCategory.innerHTML = "";
    categoriesList.forEach(cat => {
        const opt = document.createElement("option");
        opt.value = cat.name;
        opt.innerText = cat.name;
        if (cat.name === selectedCategoryName) {
            opt.selected = true;
        }
        editorCategory.appendChild(opt);
    });
}

// Add editable checklist task row inside modal
function addEditorTaskRow(text = "", completed = false) {
    if (!editorTasksList) return;
    
    const row = document.createElement("div");
    row.className = "editor-task-row";
    row.innerHTML = `
        <input type="checkbox" class="editor-task-check" ${completed ? "checked" : ""}>
        <input type="text" class="editor-task-input" placeholder="Название задачи..." required value="${text.replace(/"/g, '&quot;')}">
        <button type="button" class="editor-task-delete-btn"><i class="fa-solid fa-trash-can"></i></button>
    `;
    
    row.querySelector(".editor-task-delete-btn").addEventListener("click", () => {
        row.remove();
    });
    
    editorTasksList.appendChild(row);
}

// Open Editor in CREATE mode
function openEditorForCreate() {
    editorMode = "create";
    editingNoteId = null;
    if (editorModalTitleLabel) editorModalTitleLabel.innerText = "Новая заметка";
    
    editorTitle.value = "";
    editorSummary.value = "";
    editorReminder.value = "";
    editorTasksList.innerHTML = "";
    
    populateEditorCategoryOptions();
    addEditorTaskRow("", false); // add one default empty row
    
    editorModal.classList.add("active");
    if (tg.HapticFeedback) tg.HapticFeedback.impactOccurred("light");
}

// Open Editor in EDIT mode
function openEditorForEdit(note) {
    editorMode = "edit";
    editingNoteId = note.id;
    if (editorModalTitleLabel) editorModalTitleLabel.innerText = "Редактировать заметку";
    
    editorTitle.value = note.title || "";
    editorSummary.value = note.summary || "";
    
    // Format reminder datetime to local format YYYY-MM-DDTHH:MM
    if (note.reminder_at) {
        const d = new Date(note.reminder_at);
        const pad = (n) => n.toString().padStart(2, '0');
        const localStr = `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
        editorReminder.value = localStr;
    } else {
        editorReminder.value = "";
    }
    
    editorTasksList.innerHTML = "";
    populateEditorCategoryOptions(note.category);
    
    if (note.tasks && note.tasks.length > 0) {
        note.tasks.forEach(t => {
            const text = typeof t === "string" ? t : t.text;
            const completed = typeof t === "string" ? false : t.completed;
            addEditorTaskRow(text, completed);
        });
    } else {
        addEditorTaskRow("", false);
    }
    
    editorModal.classList.add("active");
    if (tg.HapticFeedback) tg.HapticFeedback.impactOccurred("light");
}

function closeEditorModal() {
    editorModal.classList.remove("active");
}

// Listeners
if (createNoteBtn) {
    createNoteBtn.addEventListener("click", openEditorForCreate);
}
if (closeEditorBtn) {
    closeEditorBtn.addEventListener("click", closeEditorModal);
}
if (editorAddTaskBtn) {
    editorAddTaskBtn.addEventListener("click", () => addEditorTaskRow("", false));
}

if (noteEditorForm) {
    noteEditorForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const title = editorTitle.value.trim();
        const summary = editorSummary.value.trim();
        const category = editorCategory.value;
        const reminderVal = editorReminder.value;
        
        const reminder_at = reminderVal ? new Date(reminderVal).toISOString() : null;
        
        // Build tasks array from DOM inputs
        const tasks = [];
        document.querySelectorAll("#editor-tasks-list .editor-task-row").forEach(row => {
            const text = row.querySelector(".editor-task-input").value.trim();
            const completed = row.querySelector(".editor-task-check").checked;
            if (text) {
                tasks.push({ text, completed });
            }
        });
        
        const payload = { title, summary, category, tasks, reminder_at };
        
        try {
            const base = window.API_BASE || "";
            const queryParams = tg.initData ? "" : `?user_id=${user.id}`;
            
            if (editorMode === "create") {
                const response = await fetch(`${base}/api/notes${queryParams}`, {
                    method: "POST",
                    headers: getHeaders(),
                    body: JSON.stringify(payload)
                });
                if (response.ok) {
                    const newNote = await response.json();
                    notesList.unshift(newNote);
                    closeEditorModal();
                    renderNotes();
                    if (tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
                } else {
                    showAlert("Не удалось создать заметку.");
                }
            } else if (editorMode === "edit") {
                const response = await fetch(`${base}/api/notes/${editingNoteId}${queryParams}`, {
                    method: "PUT",
                    headers: getHeaders(),
                    body: JSON.stringify(payload)
                });
                if (response.ok) {
                    const updatedNote = await response.json();
                    // Update note in array memory
                    notesList = notesList.map(n => n.id === editingNoteId ? updatedNote : n);
                    closeEditorModal();
                    renderNotes();
                    if (tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
                } else {
                    showAlert("Не удалось обновить заметку.");
                }
            }
        } catch (err) {
            console.error("Error saving note:", err);
            showAlert("Ошибка при отправке данных на сервер.");
        }
    });
}

// Refresh button interaction
refreshBtn.addEventListener("click", () => {
    loadNotes();
    if (tg.HapticFeedback) {
        tg.HapticFeedback.impactOccurred("medium");
    }
});

// Initial boot
loadNotes();
