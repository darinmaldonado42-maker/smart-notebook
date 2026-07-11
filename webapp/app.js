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
        
        let iconHtml = "";
        switch (cat.color) {
            case "idea": iconHtml = `<i class="fa-solid fa-lightbulb"></i> `; break;
            case "study": iconHtml = `<i class="fa-solid fa-graduation-cap"></i> `; break;
            case "task": iconHtml = `<i class="fa-solid fa-list-check"></i> `; break;
            case "daily": iconHtml = `<i class="fa-solid fa-house"></i> `; break;
            case "work": iconHtml = `<i class="fa-solid fa-briefcase"></i> `; break;
            case "finance": iconHtml = `<i class="fa-solid fa-wallet"></i> `; break;
            case "health": iconHtml = `<i class="fa-solid fa-heart-pulse"></i> `; break;
            case "shopping": iconHtml = `<i class="fa-solid fa-cart-shopping"></i> `; break;
            case "creative": iconHtml = `<i class="fa-solid fa-palette"></i> `; break;
            case "travel": iconHtml = `<i class="fa-solid fa-plane"></i> `; break;
            default: iconHtml = `<i class="fa-solid fa-tag"></i> `; break;
        }
        
        btn.innerHTML = `${iconHtml}${cat.name}`;
        btn.addEventListener("click", () => selectCategory(cat.name, btn));
        filtersContainer.appendChild(btn);
    });
    
    // 3. "+" add/manage category button
    const addBtn = document.createElement("button");
    addBtn.className = "filter-capsule add-category-btn";
    addBtn.innerHTML = `<i class="fa-solid fa-plus"></i>`;
    addBtn.addEventListener("click", () => openCategoriesModal());
    filtersContainer.appendChild(addBtn);
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

let selectedColor = "idea";

// Setup color option clicks in modal
document.querySelectorAll(".color-option").forEach(opt => {
    opt.addEventListener("click", () => {
        document.querySelectorAll(".color-option").forEach(o => o.classList.remove("selected"));
        opt.classList.add("selected");
        selectedColor = opt.dataset.color;
    });
});

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
                <div class="category-color-dot ${cat.color}"></div>
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
                body: JSON.stringify({ name, color: selectedColor })
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
                    evt.stopPropagation(); // prevent card expand toggle when checking a task
                    const state = taskItem.classList.toggle("checked");
                    localStorage.setItem(taskKey, state ? "true" : "false");
                    
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



// Refresh button interaction
refreshBtn.addEventListener("click", () => {
    loadNotes();
    if (tg.HapticFeedback) {
        tg.HapticFeedback.impactOccurred("medium");
    }
});

// Initial boot
loadNotes();
