// PDF.js will be loaded dynamically on first use
let pdfjsLib = null;
// Keep pdfDoc outside Alpine to avoid Proxy wrapping (PDF.js uses private fields)
let _pdfDoc = null;
// Store per-page viewports for coordinate conversion (page_number → viewport)
let _pageViewports = {};
// Debounce timer for CTRL+scroll zoom re-render
let _zoomRenderTimer = null;
// Snapshot of scroll anchor before zoom sequence begins (reset after render)
let _zoomAnchor = null;
// Debounce timers for matrix cell saves
let _matrixSaveTimers = {};
// Debounce timer for matrix filter recomputation
let _matrixFilterTimer = null;
// Raw matrix data kept outside Alpine to avoid deep Proxy wrapping (perf critical)
let _matrixRaw = null; // { columns, papers, cells, evidence }

async function ensurePdfJs() {
    if (pdfjsLib) return pdfjsLib;
    pdfjsLib = await import("https://cdn.jsdelivr.net/npm/pdfjs-dist@5.2.133/build/pdf.min.mjs");
    pdfjsLib.GlobalWorkerOptions.workerSrc =
        "https://cdn.jsdelivr.net/npm/pdfjs-dist@5.2.133/build/pdf.worker.min.mjs";
    return pdfjsLib;
}

document.addEventListener("alpine:init", () => {
    Alpine.data("app", () => ({
        // State
        papers: [],
        selectedPaperId: null,
        selectedPaper: null,
        searchQuery: "",
        statusFilter: "all",
        exclusionCodes: [],
        stats: null,
        rightTab: "details",
        dragOver: false,
        view: "papers", // "papers" | "matrix" | "themes"

        // Theme
        theme: localStorage.getItem("theme") || "night",

        // Sidebar
        sidebarOpen: localStorage.getItem("sidebarOpen") !== "false",

        // Panel widths
        leftWidth: parseInt(localStorage.getItem("leftWidth")) || 320,
        rightWidth: parseInt(localStorage.getItem("rightWidth")) || 350,
        _resizing: null,
        _resizeStartX: 0,
        _resizeStartWidth: 0,

        // Review form
        reviewForm: {
            decision: null,
            notes: "",
            exclusion_code_ids: [],
        },

        // PDF state (pdfDoc is kept outside Alpine as _pdfDoc to avoid Proxy issues)
        pdfScale: 1.0,
        _renderedScale: 1.0, // scale at which canvases were last rendered
        pdfPageCount: 0,
        pdfCurrentPage: 1,
        pdfRendering: false,
        _scrollRaf: null,

        // Coding state (v2: hierarchical codes on annotations)
        codes: [],              // top-level codes with children
        paperAnnotations: [],   // annotations for selected paper
        codingCompleteness: {},
        codeUsageCounts: {},    // {code_id: annotation_count}
        showCodeManager: false,
        newCodeName: "",
        newSubCodeNames: {},    // {parent_code_id: "name"}
        matrixColumns: [],      // matrix column definitions with options and linked codes
        matrixLoaded: false,    // flag: _matrixRaw is populated
        paperMatrixCells: {},  // {column_id: {value, notes}} for selected paper
        showColumnEditor: false,
        newColumnName: "",
        newColumnType: "enum_single",
        newOptionValues: {},   // {column_id: "value"}
        // Matrix view parameterization
        metadataColumns: [
            { key: "title", label: "Paper", pinned: true },
            { key: "author", label: "Author", pinned: false },
            { key: "year", label: "Year", pinned: true },
            { key: "venue", label: "Venue", pinned: false },
            { key: "entry_type", label: "Type", pinned: false },
            { key: "phase3_decision", label: "Status", pinned: false },
        ],
        visibleMetaCols: JSON.parse(localStorage.getItem("matrixMetaCols") || '["title","year"]'),
        visibleMatrixCols: JSON.parse(localStorage.getItem("matrixCols") || "null"),
        matrixStatusFilter: localStorage.getItem("matrixStatusFilter") || "all",
        matrixColFilters: {},
        matrixSort: { key: null, dir: "asc" }, // { key: meta key or col id, dir: "asc"|"desc" }
        matrixViewPapers: [],  // cached filtered+sorted result (plain objects, not proxied)
        matrixViewColumns: [], // cached visible matrix columns
        matrixTotalPapers: 0,  // total before filtering
        editingCell: null,

        // Themes view
        selectedThemeCodeId: null,
        themesAnnotations: [],

        // Per-paper summary
        paperSummary: [],

        // Chat
        showChat: false,
        chatMessages: [],
        chatInput: "",
        chatId: null,
        chatList: [],
        chatLoading: false,
        chatStreamContent: "",
        chatProvider: "ollama",
        chatModel: "",           // set after loading models
        llmModels: { ollama: [], claude: true },
        showChatParams: false,
        chatParams: {
            num_ctx: 32768,
            num_predict: 2048,
            temperature: 0.6,
            top_k: 20,
            top_p: 0.95,
            presence_penalty: 1.5,
        },
        _chatAbortController: null,

        // Annotation state
        selectedAnnotation: null,    // annotation detail view
        annotationReturnTab: null,   // tab to return to from annotation detail
        showAnnotationToolbar: false,
        pendingSelection: null,      // {text, rects, pageNumber}
        selectedAnnotationCodes: [], // code IDs to tag new annotation with
        pdfMode: "text",             // "hand" | "text" | "box"
        _panning: false,             // true during hand-mode drag
        addingRegionTo: null,        // annotation ID when adding regions
        annotationToolbarSearch: "", // search in annotation creation toolbar
        showCodePicker: false,       // toggle for code picker in annotation detail
        codePickerSearch: "",        // search filter for code picker

        // Toast
        toasts: [],  // [{id, msg, type}]
        _toastCounter: 0,

        // Dirty tracking for unsaved changes warning
        _reviewFormClean: null,  // snapshot of reviewForm when paper loaded

        async init() {
            this.$watch("theme", (val) => {
                document.documentElement.setAttribute("data-theme", val);
            });
            document.documentElement.setAttribute("data-theme", this.theme);
            this.$watch("visibleMetaCols", v => localStorage.setItem("matrixMetaCols", JSON.stringify(v)));
            this.$watch("visibleMatrixCols", v => localStorage.setItem("matrixCols", JSON.stringify(v)));
            this.$watch("matrixStatusFilter", v => { localStorage.setItem("matrixStatusFilter", v); this.loadMatrix(); });
            // Global keyboard shortcuts
            document.addEventListener("keydown", (e) => {
                // Don't intercept when typing in inputs
                const tag = e.target.tagName;
                const isTyping = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";

                if (e.key === "Escape") {
                    if (this.showCodePicker) { this.showCodePicker = false; return; }
                    if (this.showAnnotationToolbar) { this.cancelAnnotation(); return; }
                    if (this.selectedAnnotation) { this.selectedAnnotation = null; return; }
                    if (this.showCodeManager) { this.showCodeManager = false; return; }
                }

                // Ctrl+S / Cmd+S to save review
                if ((e.ctrlKey || e.metaKey) && e.key === "s") {
                    e.preventDefault();
                    this.saveReview();
                    return;
                }

                if (isTyping) return;

                // Mode shortcuts
                if (e.key === "h" || e.key === "H") { this.setPdfMode("hand"); e.preventDefault(); }
                if (e.key === "t" || e.key === "T") { this.setPdfMode("text"); e.preventDefault(); }
                if (e.key === "b" || e.key === "B") { this.setPdfMode("box"); e.preventDefault(); }

                // Paper navigation
                if (e.key === "ArrowLeft" || e.key === "j" || e.key === "J") { this.prevPaper(); e.preventDefault(); }
                if (e.key === "ArrowRight" || e.key === "k" || e.key === "K") { this.nextPaper(); e.preventDefault(); }
            });
            // Block browser zoom on CTRL+scroll over the whole page,
            // but only do our custom zoom when over the PDF container.
            document.addEventListener("wheel", (e) => {
                if (e.ctrlKey || e.metaKey) {
                    e.preventDefault();
                    // Only zoom if the event is inside the PDF container
                    const container = this.$refs.pdfContainer;
                    if (container && container.contains(e.target)) {
                        this.onPdfWheel(e);
                    }
                }
            }, { passive: false });
            await Promise.all([
                this.loadPapers(),
                this.loadExclusionCodes(),
                this.loadStats(),
                this.loadCodes(),
                this.loadCodingCompleteness(),
                this.loadCodeUsageCounts(),
                this.loadMatrixColumns(),
                this.loadLlmModels(),
            ]);

            // Auto-select first paper on load
            if (this.papers.length > 0 && !this.selectedPaperId) {
                const withPdf = this.papers.find(p => p.pdf_path);
                await this.selectPaper((withPdf || this.papers[0]).id);
            }
        },

        // --- Data loading ---

        async loadPapers() {
            const params = new URLSearchParams();
            if (this.searchQuery) params.set("search", this.searchQuery);
            if (this.statusFilter !== "all") params.set("status", this.statusFilter);
            const res = await fetch(`api/papers?${params}`);
            if (!res.ok) { this.showToast("Failed to load papers", "error"); return; }
            this.papers = await res.json();
            // Scroll selected paper into view after list reload
            this.$nextTick(() => {
                const el = document.querySelector(`[data-paper-id="${this.selectedPaperId}"]`);
                if (el) el.scrollIntoView({ block: "nearest" });
            });
        },

        async loadExclusionCodes() {
            const res = await fetch("api/exclusion-codes");
            if (!res.ok) return;
            this.exclusionCodes = await res.json();
        },

        async loadStats() {
            const res = await fetch("api/stats");
            if (!res.ok) return;
            this.stats = await res.json();
        },

        // --- Paper selection ---

        get isReviewDirty() {
            if (!this._reviewFormClean) return false;
            return JSON.stringify(this.reviewForm) !== this._reviewFormClean;
        },

        async selectPaper(id, force = false) {
            // Warn if unsaved changes
            if (!force && this.isReviewDirty) {
                if (!confirm("You have unsaved review changes. Discard?")) return;
            }

            this.selectedPaperId = id;
            const res = await fetch(`api/papers/${id}`);
            if (!res.ok) { this.showToast("Failed to load paper", "error"); return; }
            this.selectedPaper = await res.json();

            // Populate review form
            this.reviewForm = {
                decision: this.selectedPaper.phase3_decision || null,
                notes: this.selectedPaper.phase3_notes || "",
                exclusion_code_ids: (this.selectedPaper.exclusion_codes || []).map(
                    (c) => c.id
                ),
            };
            this._reviewFormClean = JSON.stringify(this.reviewForm);

            // Load PDF if available
            if (this.selectedPaper.pdf_path) {
                await this.loadPdf(id);
            } else {
                this.clearPdf();
            }

            // Reset chat for new paper
            this.abortChat();
            this.chatId = null;
            this.chatMessages = [];
            this.chatList = [];

            // Load annotations, matrix cells, and summary for this paper
            const loads = [
                this.loadPaperAnnotations(),
                this.loadPaperMatrixCells(),
                this.loadPaperSummary(),
            ];
            if (this.showChat) loads.push(this.loadChats());
            await Promise.all(loads);
        },

        // --- PDF ---

        async loadPdf(docId) {
            // Wait for DOM to be ready (refs need the element to exist)
            await this.$nextTick();
            let container = this.$refs.pdfPages;
            if (!container) {
                // Retry once after a short delay (DOM may still be updating)
                await new Promise(r => setTimeout(r, 50));
                container = this.$refs.pdfPages;
                if (!container) return;
            }
            container.innerHTML = "";
            _pdfDoc = null;
            this.pdfPageCount = 0;
            this.pdfCurrentPage = 1;
            this.pdfRendering = false; // cancel any in-progress render

            try {
                const pdfjs = await ensurePdfJs();
                const loadingTask = pdfjs.getDocument(`api/papers/${docId}/pdf`);
                _pdfDoc = await loadingTask.promise;
                this.pdfPageCount = _pdfDoc.numPages;

                // Fit to width initially
                const page = await _pdfDoc.getPage(1);
                const containerWidth = this.$refs.pdfContainer.clientWidth - 40;
                const viewport = page.getViewport({ scale: 1.0 });
                this.pdfScale = containerWidth / viewport.width;
                await this.buildPageStructure();
            } catch (err) {
                console.error("Failed to load PDF:", err);
                this.showToast("Failed to load PDF", "error");
            }
        },

        clearPdf() {
            const container = this.$refs?.pdfPages;
            if (container) container.innerHTML = "";
            _pdfDoc = null;
            _pageViewports = {};
            this.pdfPageCount = 0;
            this.pdfCurrentPage = 1;
        },

        async buildPageStructure() {
            if (!_pdfDoc) return;
            const container = this.$refs.pdfPages;
            container.innerHTML = "";
            _pageViewports = {};

            for (let i = 1; i <= _pdfDoc.numPages; i++) {
                const page = await _pdfDoc.getPage(i);
                const viewport = page.getViewport({ scale: this.pdfScale });
                _pageViewports[i] = viewport;

                const pageDiv = document.createElement("div");
                pageDiv.className = "pdf-page mb-2 shadow-lg";
                pageDiv.dataset.page = i;
                pageDiv.dataset.rendered = "false";
                pageDiv.style.width = viewport.width + "px";
                pageDiv.style.height = viewport.height + "px";
                pageDiv.style.position = "relative";

                container.appendChild(pageDiv);
            }

            this._renderedScale = this.pdfScale;
            await this.renderVisiblePages();
        },

        _getVisiblePages() {
            const container = this.$refs.pdfContainer;
            if (!container) return new Set();
            const pages = container.querySelectorAll(".pdf-page");
            const visibleSet = new Set();
            const containerRect = container.getBoundingClientRect();
            const bufferPx = containerRect.height; // 1 viewport height buffer

            for (const pageDiv of pages) {
                const pageRect = pageDiv.getBoundingClientRect();
                if (pageRect.bottom > containerRect.top - bufferPx &&
                    pageRect.top < containerRect.bottom + bufferPx) {
                    visibleSet.add(parseInt(pageDiv.dataset.page));
                }
            }
            return visibleSet;
        },

        async renderVisiblePages(forceRerender = false) {
            if (!_pdfDoc || this.pdfRendering) return;
            this.pdfRendering = true;

            const visibleSet = this._getVisiblePages();
            const container = this.$refs.pdfContainer;

            // Render newly visible pages in parallel
            const renderPromises = [];
            for (const pageNum of visibleSet) {
                const pageDiv = container.querySelector(`.pdf-page[data-page="${pageNum}"]`);
                if (!pageDiv) continue;
                if (pageDiv.dataset.rendered === "true" && !forceRerender) continue;
                renderPromises.push(this._renderSinglePage(pageNum, pageDiv));
            }
            await Promise.all(renderPromises);

            // Unrender far-away pages to save memory
            const allPages = container.querySelectorAll(".pdf-page");
            for (const pageDiv of allPages) {
                const num = parseInt(pageDiv.dataset.page);
                if (!visibleSet.has(num) && pageDiv.dataset.rendered === "true") {
                    this._unrenderPage(pageDiv);
                }
            }

            this.renderAnnotationOverlays(visibleSet);
            this.pdfRendering = false;
        },

        async _renderSinglePage(pageNum, pageDiv) {
            const page = await _pdfDoc.getPage(pageNum);
            const viewport = page.getViewport({ scale: this.pdfScale });
            _pageViewports[pageNum] = viewport;

            // Clear any existing content
            pageDiv.innerHTML = "";
            pageDiv.style.width = viewport.width + "px";
            pageDiv.style.height = viewport.height + "px";

            const canvas = document.createElement("canvas");
            canvas.width = viewport.width * window.devicePixelRatio;
            canvas.height = viewport.height * window.devicePixelRatio;
            canvas.style.width = viewport.width + "px";
            canvas.style.height = viewport.height + "px";

            const ctx = canvas.getContext("2d");
            ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

            pageDiv.appendChild(canvas);

            await page.render({
                canvasContext: ctx,
                viewport: viewport,
            }).promise;

            // Text layer
            const textContent = await page.getTextContent();
            const textLayerDiv = document.createElement("div");
            textLayerDiv.className = "textLayer";
            textLayerDiv.style.setProperty("--scale-factor", viewport.scale);
            textLayerDiv.style.setProperty("--total-scale-factor", viewport.scale);
            textLayerDiv.style.setProperty("--scale-round-x", "1px");
            textLayerDiv.style.setProperty("--scale-round-y", "1px");
            pageDiv.appendChild(textLayerDiv);

            const textLayer = new pdfjsLib.TextLayer({
                textContentSource: textContent,
                container: textLayerDiv,
                viewport: viewport,
            });
            textLayer.render();

            // Annotation overlay layer
            const annotOverlay = document.createElement("div");
            annotOverlay.className = "pdf-annotation-layer";
            annotOverlay.style.width = viewport.width + "px";
            annotOverlay.style.height = viewport.height + "px";
            pageDiv.appendChild(annotOverlay);

            pageDiv.dataset.rendered = "true";
        },

        _unrenderPage(pageDiv) {
            pageDiv.innerHTML = "";
            pageDiv.dataset.rendered = "false";
        },

        // --- Annotation overlay rendering ---

        renderAnnotationOverlays(visibleSet) {
            // If no visible set provided, render for all rendered pages
            if (!visibleSet) {
                visibleSet = this._getVisiblePages();
            }

            // Clear overlays only on visible pages
            for (const pageNum of visibleSet) {
                const overlay = document.querySelector(
                    `.pdf-page[data-page="${pageNum}"] .pdf-annotation-layer`
                );
                if (overlay) overlay.innerHTML = "";
            }

            for (const ann of this.paperAnnotations) {
                const rects = JSON.parse(ann.rects_json || "[]");
                const color = ann.codes?.[0]?.color || "#FFEB3B";
                const isArea = ann.annotation_type === "area";

                for (const rect of rects) {
                    const pageNum = rect.page || ann.page_number;
                    if (!visibleSet.has(pageNum)) continue;
                    const viewport = _pageViewports[pageNum];
                    if (!viewport) continue;
                    const overlay = document.querySelector(
                        `.pdf-page[data-page="${pageNum}"] .pdf-annotation-layer`
                    );
                    if (!overlay) continue;

                    const [vx1, vy1] = viewport.convertToViewportPoint(rect.x, rect.y);
                    const [vx2, vy2] = viewport.convertToViewportPoint(
                        rect.x + rect.w, rect.y + rect.h
                    );

                    const el = document.createElement("div");
                    el.className = isArea ? "pdf-area" : "pdf-highlight";
                    el.dataset.annotationId = ann.id;
                    el.style.left = Math.min(vx1, vx2) + "px";
                    el.style.top = Math.min(vy1, vy2) + "px";
                    el.style.width = Math.abs(vx2 - vx1) + "px";
                    el.style.height = Math.abs(vy2 - vy1) + "px";

                    if (isArea) {
                        el.style.border = `2px dashed ${color}`;
                        el.style.backgroundColor = color + "10";
                    } else {
                        el.style.backgroundColor = color + "30";
                        el.style.borderBottom = `1px solid ${color}80`;
                    }
                    el.title = ann.selected_text?.substring(0, 80) || ann.note?.substring(0, 80) || "";
                    overlay.appendChild(el);
                }
            }
        },

        // --- Text selection → annotation creation ---

        setPdfMode(mode) {
            this.pdfMode = mode;
            this.showAnnotationToolbar = false;
            this.annotationToolbarSearch = "";
            window.getSelection()?.removeAllRanges();
        },

        onPdfMouseDown(event) {
            if (this.pdfMode === "hand") {
                this.startHandPan(event);
            } else if (this.pdfMode === "box") {
                this.onBoxMouseDown(event);
            }
            // text mode: handled by native text selection + mouseup
        },

        startHandPan(event) {
            const container = this.$refs.pdfContainer;
            if (!container) return;
            this._panning = true;
            const startX = event.clientX;
            const startY = event.clientY;
            const startScrollLeft = container.scrollLeft;
            const startScrollTop = container.scrollTop;

            const onMove = (e) => {
                container.scrollLeft = startScrollLeft - (e.clientX - startX);
                container.scrollTop = startScrollTop - (e.clientY - startY);
            };
            const onUp = () => {
                this._panning = false;
                document.removeEventListener("mousemove", onMove);
                document.removeEventListener("mouseup", onUp);
            };
            document.addEventListener("mousemove", onMove);
            document.addEventListener("mouseup", onUp);
            event.preventDefault();
        },

        _applyZoomVisual() {
            const pagesEl = this.$refs.pdfPages;
            if (!pagesEl || this._renderedScale === 0) return;
            const transformScale = this.pdfScale / this._renderedScale;
            pagesEl.style.transformOrigin = "top center";
            pagesEl.style.transform = `scale(${transformScale})`;
            pagesEl.classList.add("pdf-pages-zooming");
        },

        async _updatePageDimensions() {
            // Update all page div sizes and viewports without destroying content
            const container = this.$refs.pdfPages;
            if (!container || !_pdfDoc) return;

            for (let i = 1; i <= _pdfDoc.numPages; i++) {
                const page = await _pdfDoc.getPage(i);
                const viewport = page.getViewport({ scale: this.pdfScale });
                _pageViewports[i] = viewport;

                const pageDiv = container.querySelector(`.pdf-page[data-page="${i}"]`);
                if (!pageDiv) continue;
                pageDiv.style.width = viewport.width + "px";
                pageDiv.style.height = viewport.height + "px";
                // Mark as stale — will be re-rendered by renderVisiblePages
                pageDiv.dataset.rendered = "false";
            }

            this._renderedScale = this.pdfScale;
        },

        _scheduleZoomRender(anchor = null) {
            clearTimeout(_zoomRenderTimer);
            _zoomRenderTimer = setTimeout(async () => {
                _zoomAnchor = null;

                // Update dimensions in-place (no DOM destruction)
                await this._updatePageDimensions();

                // Clear CSS transform now that dimensions match target scale
                const pagesEl = this.$refs.pdfPages;
                if (pagesEl) {
                    pagesEl.style.transform = "";
                    pagesEl.classList.remove("pdf-pages-zooming");
                }

                // Restore scroll position before rendering (so visible page calc is correct)
                if (anchor) {
                    const container = this.$refs.pdfContainer;
                    container.scrollLeft = anchor.contentX * this.pdfScale - anchor.cursorX;
                    container.scrollTop = anchor.contentY * this.pdfScale - anchor.cursorY;
                }

                // Re-render visible pages at the new scale (force since scale changed)
                await this.renderVisiblePages(true);
            }, 300);
        },

        onPdfWheel(event) {
            const container = this.$refs.pdfContainer;
            if (!container || !_pdfDoc) return;

            const delta = event.deltaY > 0 ? -0.1 : 0.1;
            const oldScale = this.pdfScale;
            const newScale = Math.min(Math.max(oldScale + delta, 0.5), 4.0);
            if (newScale === oldScale) return;

            // On first tick of a zoom gesture, capture the anchor point
            if (!_zoomAnchor) {
                const rect = container.getBoundingClientRect();
                const cursorX = event.clientX - rect.left;
                const cursorY = event.clientY - rect.top;
                _zoomAnchor = {
                    contentX: (container.scrollLeft + cursorX) / oldScale,
                    contentY: (container.scrollTop + cursorY) / oldScale,
                    cursorX,
                    cursorY,
                };
            }

            this.pdfScale = newScale;
            this._applyZoomVisual();
            this._scheduleZoomRender(_zoomAnchor);
        },

        onTextSelection(event) {
            if (this.pdfMode !== "text") return;
            // If toolbar is already showing, don't interfere (user is clicking inside toolbar)
            if (this.showAnnotationToolbar) return;

            const sel = window.getSelection();
            if (!sel || sel.isCollapsed || !sel.toString().trim()) {
                this.checkAnnotationClick(event);
                return;
            }

            const text = sel.toString().trim();
            const range = sel.getRangeAt(0);
            const clientRects = range.getClientRects();
            if (clientRects.length === 0) return;

            // Find which page the selection is on by traversing from the anchor node
            const pageDiv = sel.anchorNode?.parentElement?.closest(".pdf-page");
            if (!pageDiv) return;
            const pageNumber = parseInt(pageDiv.dataset.page);
            const viewport = _pageViewports[pageNumber];
            if (!viewport) return;

            // Convert viewport rects → PDF coordinate space
            const pageBounds = pageDiv.getBoundingClientRect();
            const pdfRects = [];
            for (const cr of clientRects) {
                const relX = cr.left - pageBounds.left;
                const relY = cr.top - pageBounds.top;
                const relX2 = relX + cr.width;
                const relY2 = relY + cr.height;

                const [px1, py1] = viewport.convertToPdfPoint(relX, relY);
                const [px2, py2] = viewport.convertToPdfPoint(relX2, relY2);

                pdfRects.push({
                    x: Math.min(px1, px2),
                    y: Math.min(py1, py2),
                    w: Math.abs(px2 - px1),
                    h: Math.abs(py2 - py1),
                });
            }

            // Store pending selection and show toolbar
            this.pendingSelection = { text, rects: pdfRects, pageNumber };
            this.selectedAnnotationCodes = [];

            this.showAnnotationToolbar = true;
            this.$nextTick(() => this.$refs.annotationToolbarSearchInput?.focus({ preventScroll: true }));
        },

        toggleAnnotationCode(codeId) {
            const idx = this.selectedAnnotationCodes.indexOf(codeId);
            if (idx >= 0) {
                this.selectedAnnotationCodes = this.selectedAnnotationCodes.filter(id => id !== codeId);
            } else {
                this.selectedAnnotationCodes = [...this.selectedAnnotationCodes, codeId];
            }
        },

        async confirmAnnotation() {
            if (!this.pendingSelection || !this.selectedPaperId) return;

            const { text, rects, pageNumber } = this.pendingSelection;

            // If adding region to existing annotation
            if (this.addingRegionTo) {
                await this.appendRegionToAnnotation(this.addingRegionTo, rects, pageNumber, text);
                window.getSelection()?.removeAllRanges();
                this.showAnnotationToolbar = false;
                this.pendingSelection = null;
                this.showToast("Region added", "success");
                return;
            }

            // Tag rects with page numbers
            const taggedRects = rects.map(r => ({ ...r, page: pageNumber }));
            const annType = text ? "highlight" : "area";

            const codeIds = [...this.selectedAnnotationCodes];
            const res = await fetch(`api/papers/${this.selectedPaperId}/annotations`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    annotation_type: annType,
                    page_number: pageNumber,
                    selected_text: text,
                    rects_json: JSON.stringify(taggedRects),
                    code_ids: codeIds,
                }),
            });
            window.getSelection()?.removeAllRanges();
            this.showAnnotationToolbar = false;
            this.annotationToolbarSearch = "";
            this.pendingSelection = null;
            await this.loadPaperAnnotations();
            this.renderAnnotationOverlays();

            // Open the newly created annotation in detail view (without scrolling)
            if (this.paperAnnotations.length > 0) {
                const newest = this.paperAnnotations[this.paperAnnotations.length - 1];
                this.rightTab = "annotations";
                this.selectedAnnotation = newest; // don't call openAnnotationDetail to avoid scroll
            }
            this.showToast("Annotation created", "success");
        },

        cancelAnnotation() {
            window.getSelection()?.removeAllRanges();
            this.showAnnotationToolbar = false;
            this.pendingSelection = null;
        },

        checkAnnotationClick(event) {
            // Check if click point overlaps with any annotation highlight
            const pageDiv = event.target.closest(".pdf-page");
            if (!pageDiv) return;
            const pageNumber = parseInt(pageDiv.dataset.page);
            const viewport = _pageViewports[pageNumber];
            if (!viewport) return;

            const pageBounds = pageDiv.getBoundingClientRect();
            const clickX = event.clientX - pageBounds.left;
            const clickY = event.clientY - pageBounds.top;
            const [pdfX, pdfY] = viewport.convertToPdfPoint(clickX, clickY);

            for (const ann of this.paperAnnotations) {
                const rects = JSON.parse(ann.rects_json || "[]");
                for (const rect of rects) {
                    const rPage = rect.page || ann.page_number;
                    if (rPage !== pageNumber) continue;
                    // Check if click is inside this rect (PDF coordinates, y can be inverted)
                    const minX = rect.x, maxX = rect.x + rect.w;
                    const minY = Math.min(rect.y, rect.y + rect.h);
                    const maxY = Math.max(rect.y, rect.y + rect.h);
                    if (pdfX >= minX && pdfX <= maxX && pdfY >= minY && pdfY <= maxY) {
                        this.rightTab = "annotations";
                        this.openAnnotationDetail(ann);
                        return;
                    }
                }
            }
        },

        scrollToAnnotation(ann) {
            const pageDiv = document.querySelector(`.pdf-page[data-page="${ann.page_number}"]`);
            if (pageDiv) {
                pageDiv.scrollIntoView({ behavior: "smooth", block: "center" });
            }
        },

        pdfZoomIn() {
            this.pdfScale = Math.min(this.pdfScale + 0.25, 4.0);
            this._applyZoomVisual();
            this._scheduleZoomRender();
        },

        pdfZoomOut() {
            this.pdfScale = Math.max(this.pdfScale - 0.25, 0.5);
            this._applyZoomVisual();
            this._scheduleZoomRender();
        },

        async pdfFitWidth() {
            if (!_pdfDoc) return;
            const page = await _pdfDoc.getPage(1);
            const container = this.$refs.pdfContainer;
            const containerWidth = container.clientWidth - 40;
            const viewport = page.getViewport({ scale: 1.0 });
            this.pdfScale = containerWidth / viewport.width;
            this._applyZoomVisual();
            this._scheduleZoomRender();
        },

        onPdfScroll() {
            if (this._scrollRaf) return;
            this._scrollRaf = requestAnimationFrame(() => {
                this._scrollRaf = null;
                this._updateCurrentPage();
                this.renderVisiblePages();
            });
        },

        _updateCurrentPage() {
            const container = this.$refs.pdfContainer;
            const pages = container.querySelectorAll(".pdf-page");
            const scrollTop = container.scrollTop + container.clientHeight / 3;

            for (const page of pages) {
                if (page.offsetTop + page.offsetHeight > scrollTop) {
                    this.pdfCurrentPage = parseInt(page.dataset.page);
                    break;
                }
            }
        },

        // --- PDF Upload ---

        async uploadPdf(file) {
            if (!file || !this.selectedPaperId) return;
            const formData = new FormData();
            formData.append("pdf", file);

            try {
                const res = await fetch(
                    `api/papers/${this.selectedPaperId}/upload-pdf`,
                    { method: "POST", body: formData }
                );
                const data = await res.json();
                if (data.success) {
                    this.showToast("PDF uploaded", "success");
                    // Reload paper and PDF
                    await this.selectPaper(this.selectedPaperId);
                    await this.loadPapers();
                    await this.loadStats();
                } else {
                    this.showToast(data.error || "Upload failed", "error");
                }
            } catch (err) {
                this.showToast("Upload failed", "error");
            }
        },

        handleDrop(event) {
            this.dragOver = false;
            const files = event.dataTransfer.files;
            if (files.length > 0 && this.selectedPaperId) {
                this.uploadPdf(files[0]);
            }
        },

        // --- Review ---

        toggleExclusionCode(id) {
            const idx = this.reviewForm.exclusion_code_ids.indexOf(id);
            if (idx >= 0) {
                this.reviewForm.exclusion_code_ids.splice(idx, 1);
            } else {
                this.reviewForm.exclusion_code_ids.push(id);
            }
        },

        async saveReview() {
            if (!this.selectedPaperId || !this.reviewForm.decision) return;

            try {
                const res = await fetch(
                    `api/papers/${this.selectedPaperId}/review`,
                    {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(this.reviewForm),
                    }
                );
                const data = await res.json();
                if (data.success) {
                    this.showToast("Review saved", "success");
                    this._reviewFormClean = JSON.stringify(this.reviewForm);
                    await this.loadPapers();
                    await this.loadStats();
                    // Update selected paper state
                    this.selectedPaper.phase3_decision = this.reviewForm.decision;
                    this.selectedPaper.phase3_notes = this.reviewForm.notes;
                } else {
                    this.showToast(data.error || "Save failed", "error");
                }
            } catch (err) {
                this.showToast("Save failed", "error");
            }
        },

        // --- Sidebar & Paper Navigation ---

        toggleSidebar() {
            this.sidebarOpen = !this.sidebarOpen;
            localStorage.setItem("sidebarOpen", this.sidebarOpen);
        },

        get currentPaperIndex() {
            if (!this.selectedPaperId) return -1;
            return this.papers.findIndex(p => p.id === this.selectedPaperId);
        },

        async nextPaper() {
            if (this.papers.length === 0) return;
            const idx = this.currentPaperIndex;
            const nextIdx = idx < this.papers.length - 1 ? idx + 1 : 0;
            await this.selectPaper(this.papers[nextIdx].id);
        },

        async prevPaper() {
            if (this.papers.length === 0) return;
            const idx = this.currentPaperIndex;
            const prevIdx = idx > 0 ? idx - 1 : this.papers.length - 1;
            await this.selectPaper(this.papers[prevIdx].id);
        },

        // --- Theme ---

        toggleTheme() {
            this.theme = this.theme === "night" ? "light" : "night";
            localStorage.setItem("theme", this.theme);
        },

        // --- Resize ---

        startResize(side, event) {
            this._resizing = side;
            this._resizeStartX = event.clientX;
            this._resizeStartWidth = side === "left" ? this.leftWidth : this.rightWidth;

            const onMouseMove = (e) => {
                const dx = e.clientX - this._resizeStartX;
                if (this._resizing === "left") {
                    this.leftWidth = Math.max(200, Math.min(600, this._resizeStartWidth + dx));
                    localStorage.setItem("leftWidth", this.leftWidth);
                } else {
                    this.rightWidth = Math.max(250, Math.min(700, this._resizeStartWidth - dx));
                    localStorage.setItem("rightWidth", this.rightWidth);
                }
            };

            const onMouseUp = () => {
                this._resizing = null;
                document.removeEventListener("mousemove", onMouseMove);
                document.removeEventListener("mouseup", onMouseUp);
            };

            document.addEventListener("mousemove", onMouseMove);
            document.addEventListener("mouseup", onMouseUp);
        },

        // --- Codes (hierarchical) ---

        get allCodesFlat() {
            // Flatten code tree for use in annotation tagging UI
            const flat = [];
            for (const code of this.codes) {
                flat.push(code);
                for (const child of code.children || []) {
                    flat.push(child);
                }
            }
            return flat;
        },

        async loadCodes() {
            const res = await fetch("api/codes");
            if (!res.ok) return;
            this.codes = await res.json();
        },

        async createTopCode() {
            if (!this.newCodeName.trim()) return;
            const res = await fetch("api/codes", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name: this.newCodeName.trim() }),
            });
            if (res.ok) {
                this.newCodeName = "";
                await this.loadCodes();
                this.showToast("Code created", "success");
            } else {
                const err = await res.json();
                this.showToast(err.error || "Failed", "error");
            }
        },

        async createSubCode(parentId) {
            const name = this.newSubCodeNames[parentId]?.trim();
            if (!name) return;
            const res = await fetch("api/codes", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name, parent_id: parentId }),
            });
            if (res.ok) {
                this.newSubCodeNames[parentId] = "";
                await this.loadCodes();
            } else {
                const err = await res.json();
                this.showToast(err.error || "Failed", "error");
            }
        },

        async updateCode(codeId, updates) {
            await fetch(`api/codes/${codeId}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(updates),
            });
            await this.loadCodes();
        },

        async deleteCode(codeId) {
            const res = await fetch(`api/codes/${codeId}`, { method: "DELETE" });
            if (res.ok) {
                await this.loadCodes();
                await this.loadCodeUsageCounts();
            } else {
                const err = await res.json();
                this.showToast(err.error || "Code has annotations or sub-codes", "error");
            }
        },

        async loadCodeUsageCounts() {
            const res = await fetch("api/codes/usage");
            if (!res.ok) return;
            this.codeUsageCounts = await res.json();
        },

        async reorderCode(codeId, direction) {
            // Find the code and its siblings
            let siblings, idx;
            for (const code of this.codes) {
                if (code.id === codeId) {
                    siblings = this.codes;
                    idx = siblings.indexOf(code);
                    break;
                }
                const childIdx = code.children.findIndex(c => c.id === codeId);
                if (childIdx >= 0) {
                    siblings = code.children;
                    idx = childIdx;
                    break;
                }
            }
            if (!siblings || idx === undefined) return;

            const swapIdx = idx + direction;
            if (swapIdx < 0 || swapIdx >= siblings.length) return;

            // Swap sort_order values
            const a = siblings[idx], b = siblings[swapIdx];
            await Promise.all([
                this.updateCode(a.id, { sort_order: swapIdx }),
                this.updateCode(b.id, { sort_order: idx }),
            ]);
        },

        // --- Annotations ---

        async loadPaperAnnotations() {
            if (!this.selectedPaperId) return;
            const res = await fetch(`api/papers/${this.selectedPaperId}/annotations`);
            if (!res.ok) { this.showToast("Failed to load annotations", "error"); return; }
            this.paperAnnotations = await res.json();
            // Re-render overlays if PDF is loaded
            if (Object.keys(_pageViewports).length > 0) {
                this.renderAnnotationOverlays();
            }
        },

        async deleteAnnotation(annId) {
            await fetch(`api/annotations/${annId}`, { method: "DELETE" });
            await this.loadPaperAnnotations();
        },

        codeMatchesSearch(topCode) {
            const q = (this.codePickerSearch || this.annotationToolbarSearch).toLowerCase();
            if (!q) return true;
            if (topCode.name.toLowerCase().includes(q)) return true;
            if (topCode.description?.toLowerCase().includes(q)) return true;
            return (topCode.children || []).some(c => c.name.toLowerCase().includes(q));
        },

        subCodeMatchesSearch(sub, topCode) {
            const q = (this.codePickerSearch || this.annotationToolbarSearch).toLowerCase();
            if (!q) return true;
            return sub.name.toLowerCase().includes(q) || topCode.name.toLowerCase().includes(q);
        },

        async applyCodeToSelectedAnnotation(codeId) {
            if (!this.selectedAnnotation) return;
            const annId = this.selectedAnnotation.id;
            // Don't close picker — allows multi-select
            await this.addAnnotationCode(annId, codeId);
        },

        async addAnnotationCode(annId, codeId) {
            await fetch(`api/annotations/${annId}/codes/${codeId}`, { method: "POST" });
            await this.loadPaperAnnotations();
            await this.loadCodeUsageCounts();
            if (this.selectedAnnotation?.id === annId) {
                this.selectedAnnotation = this.paperAnnotations.find(a => a.id === annId);
            }
        },

        async removeAnnotationCode(annId, codeId) {
            await fetch(`api/annotations/${annId}/codes/${codeId}`, { method: "DELETE" });
            await this.loadPaperAnnotations();
            await this.loadCodeUsageCounts();
            if (this.selectedAnnotation?.id === annId) {
                this.selectedAnnotation = this.paperAnnotations.find(a => a.id === annId);
            }
        },

        async saveAnnotationCodeNote(annId, codeId, note) {
            await fetch(`api/annotations/${annId}/codes/${codeId}/note`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ note }),
            });
            // Update local state
            const ann = this.paperAnnotations.find(a => a.id === annId);
            if (ann) {
                const c = ann.codes.find(c => c.id === codeId);
                if (c) c.ac_note = note;
            }
            if (this.selectedAnnotation?.id === annId) {
                const c = this.selectedAnnotation.codes.find(c => c.id === codeId);
                if (c) c.ac_note = note;
            }
        },

        // --- Annotation detail view ---

        openAnnotationDetail(ann) {
            this.selectedAnnotation = ann;
            this.scrollToAnnotation(ann);
        },

        get annotationRegions() {
            if (!this.selectedAnnotation) return [];
            const rects = JSON.parse(this.selectedAnnotation.rects_json || "[]");
            const isArea = this.selectedAnnotation.annotation_type === "area";

            if (isArea) {
                // Area annotations: one region per rect group (by page)
                const pageGroups = {};
                for (const r of rects) {
                    const page = r.page || this.selectedAnnotation.page_number;
                    if (!pageGroups[page]) pageGroups[page] = [];
                    pageGroups[page].push(r);
                }
                return Object.entries(pageGroups)
                    .sort((a, b) => a[0] - b[0])
                    .map(([page, pageRects]) => ({
                        page: parseInt(page),
                        type: "area",
                        text: null,
                    }));
            }

            // Text highlights: split by " ... " separator (each segment = one region added)
            const texts = (this.selectedAnnotation.selected_text || "").split(" ... ").filter(t => t.trim());
            if (texts.length <= 1) {
                // Single region — all rects belong to one selection
                return [{
                    page: rects[0]?.page || this.selectedAnnotation.page_number,
                    type: "text",
                    text: this.selectedAnnotation.selected_text,
                }];
            }
            // Multiple regions (from "Add region")
            // Try to match texts to page groups
            const pageGroups = {};
            for (const r of rects) {
                const page = r.page || this.selectedAnnotation.page_number;
                if (!pageGroups[page]) pageGroups[page] = [];
                pageGroups[page].push(r);
            }
            const pages = Object.keys(pageGroups).sort((a, b) => a - b);
            return texts.map((text, i) => ({
                page: parseInt(pages[Math.min(i, pages.length - 1)]) || this.selectedAnnotation.page_number,
                type: "text",
                text: text.trim(),
            }));
        },

        async saveAnnotationNote(annId, note) {
            await fetch(`api/annotations/${annId}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ note }),
            });
            // Update local state without full reload
            const ann = this.paperAnnotations.find(a => a.id === annId);
            if (ann) ann.note = note;
            if (this.selectedAnnotation?.id === annId) this.selectedAnnotation.note = note;
        },

        // --- Multi-region: add region to existing annotation ---

        startAddRegion() {
            if (!this.selectedAnnotation) return;
            this.addingRegionTo = this.selectedAnnotation.id;
            this.showToast("Select text or draw a box to add a region", "info");
        },

        async appendRegionToAnnotation(annId, newRects, pageNumber, newText) {
            const ann = this.paperAnnotations.find(a => a.id === annId);
            if (!ann) return;

            // Merge rects — add page number to new rects
            const existingRects = JSON.parse(ann.rects_json || "[]");
            const taggedNewRects = newRects.map(r => ({ ...r, page: pageNumber }));
            // Tag existing rects with their page if not already tagged
            const taggedExisting = existingRects.map(r => r.page ? r : { ...r, page: ann.page_number });
            const mergedRects = [...taggedExisting, ...taggedNewRects];

            // Merge text
            const mergedText = ann.selected_text
                ? ann.selected_text + " ... " + (newText || "")
                : newText || ann.selected_text;

            await fetch(`api/annotations/${annId}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    rects_json: JSON.stringify(mergedRects),
                    selected_text: mergedText,
                }),
            });

            this.addingRegionTo = null;
            await this.loadPaperAnnotations();
            this.selectedAnnotation = this.paperAnnotations.find(a => a.id === annId);
            this.renderAnnotationOverlays();
        },

        // --- Box drawing for area annotations ---

        onBoxMouseDown(event) {
            const pageDiv = event.target.closest(".pdf-page");
            if (!pageDiv) return;

            const pageBounds = pageDiv.getBoundingClientRect();
            const startX = event.clientX - pageBounds.left;
            const startY = event.clientY - pageBounds.top;
            const pageNumber = parseInt(pageDiv.dataset.page);

            // Create temporary box element
            const box = document.createElement("div");
            box.className = "pdf-box-drawing";
            box.style.left = startX + "px";
            box.style.top = startY + "px";
            const overlay = pageDiv.querySelector(".pdf-annotation-layer");
            if (overlay) overlay.appendChild(box);

            const onMove = (e) => {
                const curX = e.clientX - pageBounds.left;
                const curY = e.clientY - pageBounds.top;
                box.style.left = Math.min(startX, curX) + "px";
                box.style.top = Math.min(startY, curY) + "px";
                box.style.width = Math.abs(curX - startX) + "px";
                box.style.height = Math.abs(curY - startY) + "px";
            };

            const onUp = (e) => {
                document.removeEventListener("mousemove", onMove);
                document.removeEventListener("mouseup", onUp);
                box.remove();

                const endX = e.clientX - pageBounds.left;
                const endY = e.clientY - pageBounds.top;
                const w = Math.abs(endX - startX);
                const h = Math.abs(endY - startY);
                if (w < 10 || h < 10) { this.setPdfMode("text"); return; } // too small

                const viewport = _pageViewports[pageNumber];
                if (!viewport) return;

                const [px1, py1] = viewport.convertToPdfPoint(Math.min(startX, endX), Math.min(startY, endY));
                const [px2, py2] = viewport.convertToPdfPoint(Math.max(startX, endX), Math.max(startY, endY));

                const pdfRects = [{
                    page: pageNumber,
                    x: Math.min(px1, px2),
                    y: Math.min(py1, py2),
                    w: Math.abs(px2 - px1),
                    h: Math.abs(py2 - py1),
                }];

                if (this.addingRegionTo) {
                    this.appendRegionToAnnotation(this.addingRegionTo, pdfRects, pageNumber, null);
                } else {
                    this.pendingSelection = { text: null, rects: pdfRects, pageNumber };
                    this.selectedAnnotationCodes = [];
                    this.showAnnotationToolbar = true;
                    this.$nextTick(() => this.$refs.annotationToolbarSearchInput?.focus({ preventScroll: true }));
                }
                this.setPdfMode("text");
            };

            document.addEventListener("mousemove", onMove);
            document.addEventListener("mouseup", onUp);
            event.preventDefault();
        },

        // --- Matrix Columns ---

        async loadMatrixColumns() {
            const res = await fetch("api/matrix-columns");
            if (!res.ok) return;
            this.matrixColumns = await res.json();
        },

        async createMatrixColumn() {
            if (!this.newColumnName.trim()) return;
            const res = await fetch("api/matrix-columns", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: this.newColumnName.trim(),
                    column_type: this.newColumnType,
                }),
            });
            if (res.ok) {
                this.newColumnName = "";
                await this.loadMatrixColumns();
                this.showToast("Column created", "success");
            } else {
                const err = await res.json();
                this.showToast(err.error || "Failed", "error");
            }
        },

        async updateMatrixColumn(colId, updates) {
            await fetch(`api/matrix-columns/${colId}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(updates),
            });
            await this.loadMatrixColumns();
        },

        async deleteMatrixColumn(colId) {
            const res = await fetch(`api/matrix-columns/${colId}`, { method: "DELETE" });
            if (res.ok) {
                await this.loadMatrixColumns();
                this.showToast("Column deleted", "success");
            } else {
                this.showToast("Failed to delete column", "error");
            }
        },

        async addColumnOption(colId) {
            const value = this.newOptionValues[colId]?.trim();
            if (!value) return;
            const res = await fetch(`api/matrix-columns/${colId}/options`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ value }),
            });
            if (res.ok) {
                this.newOptionValues[colId] = "";
                await this.loadMatrixColumns();
            }
        },

        async deleteColumnOption(optId) {
            await fetch(`api/matrix-column-options/${optId}`, { method: "DELETE" });
            await this.loadMatrixColumns();
        },

        async linkColumnCode(colId, codeId) {
            await fetch(`api/matrix-columns/${colId}/codes/${codeId}`, { method: "POST" });
            await this.loadMatrixColumns();
        },

        async unlinkColumnCode(colId, codeId) {
            await fetch(`api/matrix-columns/${colId}/codes/${codeId}`, { method: "DELETE" });
            await this.loadMatrixColumns();
        },

        // --- Matrix Data ---

        async loadCodingCompleteness() {
            const res = await fetch("api/coding/completeness");
            if (!res.ok) return;
            this.codingCompleteness = await res.json();
        },

        async loadMatrix() {
            const params = new URLSearchParams();
            if (this.matrixStatusFilter !== "all") params.set("status", this.matrixStatusFilter);
            const res = await fetch("api/matrix?" + params);
            if (!res.ok) { this.showToast("Failed to load matrix", "error"); return; }
            // Store raw data OUTSIDE Alpine to avoid deep Proxy wrapping
            _matrixRaw = await res.json();
            this.matrixLoaded = true;
            this.matrixTotalPapers = _matrixRaw.papers.length;
            this.matrixColFilters = {};
            this._recomputeMatrixView();
        },

        get activeMetaCols() {
            return this.metadataColumns.filter(mc => this.visibleMetaCols.includes(mc.key));
        },

        _updateVisibleColumns() {
            if (!_matrixRaw) { this.matrixViewColumns = []; return; }
            if (!this.visibleMatrixCols) {
                this.matrixViewColumns = _matrixRaw.columns;
            } else {
                this.matrixViewColumns = _matrixRaw.columns.filter(c => this.visibleMatrixCols.includes(c.id));
            }
        },

        // Debounced filter input — called from @input on text filters
        onMatrixFilterInput(key, value) {
            this.matrixColFilters[key] = value;
            clearTimeout(_matrixFilterTimer);
            _matrixFilterTimer = setTimeout(() => this._recomputeMatrixView(), 150);
        },

        // Instant filter — called from @change on select filters
        onMatrixFilterChange(key, value) {
            this.matrixColFilters[key] = value;
            this._recomputeMatrixView();
        },

        _recomputeMatrixView() {
            if (!_matrixRaw) { this.matrixViewPapers = []; this.matrixViewColumns = []; return; }
            this._updateVisibleColumns();
            const metaKeys = new Set(["title", "author", "year", "venue", "entry_type", "phase3_decision"]);
            const cells = _matrixRaw.cells;
            const columns = _matrixRaw.columns;
            // Build active filters once
            const filters = [];
            for (const [key, val] of Object.entries(this.matrixColFilters)) {
                if (!val) continue;
                const isMetaKey = metaKeys.has(key);
                const f = { key, lv: val.toLowerCase(), isMetaKey };
                if (!isMetaKey) {
                    f.colId = parseInt(key);
                    f.col = columns.find(c => c.id === f.colId);
                }
                filters.push(f);
            }
            // Filter
            let papers = _matrixRaw.papers;
            if (filters.length > 0) {
                papers = papers.filter(p => {
                    for (const f of filters) {
                        if (f.isMetaKey) {
                            if (!String(p[f.key] || "").toLowerCase().includes(f.lv)) return false;
                        } else {
                            const cellVal = cells[p.id]?.[f.colId]?.value || "";
                            if (f.col?.column_type === "enum_multi") {
                                try {
                                    if (!JSON.parse(cellVal || "[]").some(v => v.toLowerCase().includes(f.lv))) return false;
                                } catch { return false; }
                            } else {
                                if (!cellVal.toLowerCase().includes(f.lv)) return false;
                            }
                        }
                    }
                    return true;
                });
            }
            // Sort
            const { key: sortKey, dir } = this.matrixSort;
            if (sortKey != null) {
                const mult = dir === "asc" ? 1 : -1;
                const isMeta = metaKeys.has(sortKey);
                const sortColId = isMeta ? null : parseInt(sortKey);
                papers = [...papers].sort((a, b) => {
                    let va, vb;
                    if (isMeta) {
                        va = String(a[sortKey] || "").toLowerCase();
                        vb = String(b[sortKey] || "").toLowerCase();
                    } else {
                        va = (cells[a.id]?.[sortColId]?.value || "").toLowerCase();
                        vb = (cells[b.id]?.[sortColId]?.value || "").toLowerCase();
                    }
                    if (va < vb) return -1 * mult;
                    if (va > vb) return 1 * mult;
                    return 0;
                });
            }
            this.matrixViewPapers = papers;
        },

        toggleMatrixSort(key) {
            if (this.matrixSort.key === key) {
                this.matrixSort.dir = this.matrixSort.dir === "asc" ? "desc" : "asc";
            } else {
                this.matrixSort = { key, dir: "asc" };
            }
            this._recomputeMatrixView();
        },

        get hasActiveFilters() {
            return Object.values(this.matrixColFilters).some(v => v);
        },

        clearMatrixFilters() {
            this.matrixColFilters = {};
            this._recomputeMatrixView();
        },

        toggleMetaCol(key) {
            const idx = this.visibleMetaCols.indexOf(key);
            if (idx >= 0) this.visibleMetaCols.splice(idx, 1);
            else this.visibleMetaCols.push(key);
            this._updateVisibleColumns();
        },

        toggleMatrixCol(colId) {
            if (!this.visibleMatrixCols) {
                this.visibleMatrixCols = _matrixRaw.columns.map(c => c.id).filter(id => id !== colId);
            } else {
                const idx = this.visibleMatrixCols.indexOf(colId);
                if (idx >= 0) this.visibleMatrixCols.splice(idx, 1);
                else this.visibleMatrixCols.push(colId);
                if (_matrixRaw && this.visibleMatrixCols.length === _matrixRaw.columns.length) {
                    this.visibleMatrixCols = null;
                }
            }
            this._updateVisibleColumns();
        },

        // Cell value accessors — read from _matrixRaw (no Proxy overhead)
        cellVal(paperId, colId) {
            return _matrixRaw?.cells[paperId]?.[colId]?.value || "";
        },

        cellEvidence(paperId, colId) {
            return _matrixRaw?.evidence[paperId]?.[colId] || 0;
        },

        isEditingCell(docId, colId) {
            return this.editingCell?.docId === docId && this.editingCell?.colId === colId;
        },

        startEditCell(docId, colId) {
            this.editingCell = { docId, colId };
        },

        stopEditCell() {
            this.editingCell = null;
        },

        matrixDistinctValues(key) {
            if (!_matrixRaw) return [];
            const vals = new Set();
            for (const p of _matrixRaw.papers) {
                const v = p[key];
                if (v != null && v !== "") vals.add(String(v));
            }
            return [...vals].sort();
        },

        saveMatrixCell(docId, colId, value) {
            // Update raw state immediately (no Proxy)
            if (!_matrixRaw.cells[docId]) _matrixRaw.cells[docId] = {};
            _matrixRaw.cells[docId][colId] = { value, notes: null };
            // Debounce the API call
            const key = `${docId}-${colId}`;
            clearTimeout(_matrixSaveTimers[key]);
            _matrixSaveTimers[key] = setTimeout(() => {
                fetch("api/matrix/cell", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ document_id: docId, column_id: colId, value }),
                });
                delete _matrixSaveTimers[key];
            }, 500);
        },

        async loadPaperMatrixCells() {
            if (!this.selectedPaperId) return;
            const res = await fetch(`api/papers/${this.selectedPaperId}/matrix-cells`);
            if (!res.ok) return;
            this.paperMatrixCells = await res.json();
        },

        savePaperMatrixCell(colId, value) {
            // Update local state immediately
            if (!this.paperMatrixCells[colId]) this.paperMatrixCells[colId] = {};
            this.paperMatrixCells[colId].value = value;
            // Debounce the API call
            const docId = this.selectedPaperId;
            const key = `p-${docId}-${colId}`;
            clearTimeout(_matrixSaveTimers[key]);
            _matrixSaveTimers[key] = setTimeout(() => {
                fetch("api/matrix/cell", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ document_id: docId, column_id: colId, value }),
                });
                delete _matrixSaveTimers[key];
            }, 500);
        },

        toggleMultiValue(colId, optValue, scope = "paper") {
            const cells = scope === "paper" ? this.paperMatrixCells : (_matrixRaw?.cells || {});
            const docId = scope === "paper" ? this.selectedPaperId : null;

            let current = [];
            try {
                const raw = scope === "paper"
                    ? (this.paperMatrixCells[colId]?.value || "[]")
                    : (cells[docId]?.[colId]?.value || "[]");
                current = JSON.parse(raw);
            } catch { current = []; }

            const idx = current.indexOf(optValue);
            if (idx >= 0) current.splice(idx, 1);
            else current.push(optValue);

            const newValue = JSON.stringify(current);
            if (scope === "paper") {
                this.savePaperMatrixCell(colId, newValue);
            }
        },

        parseMultiValue(val) {
            try { return JSON.parse(val || "[]"); } catch { return []; }
        },

        getEvidenceForColumn(column) {
            if (!column.linked_codes?.length) return [];
            const codeIds = new Set();
            for (const lc of column.linked_codes) {
                codeIds.add(lc.id);
                // Also include sub-codes
                for (const code of this.codes) {
                    if (code.id === lc.id) {
                        for (const ch of code.children || []) codeIds.add(ch.id);
                    }
                    for (const ch of code.children || []) {
                        if (ch.id === lc.id) codeIds.add(ch.id);
                    }
                }
            }
            return this.paperAnnotations.filter(ann =>
                ann.codes.some(c => codeIds.has(c.id))
            );
        },

        // --- Themes ---

        async loadThemes(codeId) {
            this.selectedThemeCodeId = codeId;
            const res = await fetch(`api/themes/${codeId}`);
            if (!res.ok) { this.showToast("Failed to load themes", "error"); return; }
            this.themesAnnotations = await res.json();
        },

        async navigateToAnnotation(docId, annPageNumber) {
            this.view = "papers";
            await this.selectPaper(docId, true);
            this.$nextTick(() => {
                const pageDiv = document.querySelector(`.pdf-page[data-page="${annPageNumber}"]`);
                if (pageDiv) pageDiv.scrollIntoView({ behavior: "smooth", block: "center" });
            });
        },

        // --- Per-paper Summary ---

        async loadPaperSummary() {
            if (!this.selectedPaperId) return;
            const res = await fetch(`api/papers/${this.selectedPaperId}/summary`);
            if (!res.ok) return;
            this.paperSummary = await res.json();
        },

        // --- Chat ---

        async loadLlmModels() {
            const res = await fetch("api/llm/models");
            if (!res.ok) return;
            const data = await res.json();
            this.llmModels = { ollama: data.ollama || [], claude: data.claude };
            if (data.default_params) {
                this.chatParams = { ...this.chatParams, ...data.default_params };
            }
            // Auto-select first Ollama model if none set
            if (!this.chatModel && this.llmModels.ollama.length > 0) {
                this.chatModel = this.llmModels.ollama[0];
            }
        },

        abortChat() {
            if (this._chatAbortController) {
                this._chatAbortController.abort();
                this._chatAbortController = null;
            }
            this.chatLoading = false;
            this.chatStreamContent = "";
        },

        toggleChat() {
            this.showChat = !this.showChat;
            if (this.showChat && this.selectedPaperId) {
                this.loadChats();
            } else {
                this.abortChat();
            }
        },

        async loadChats() {
            if (!this.selectedPaperId) return;
            const res = await fetch(`api/papers/${this.selectedPaperId}/chats`);
            if (!res.ok) return;
            this.chatList = await res.json();
            // Auto-select most recent chat if none selected
            if (!this.chatId && this.chatList.length > 0) {
                await this.loadChatMessages(this.chatList[0].id);
            }
        },

        async loadChatMessages(chatId) {
            this.abortChat();
            this.chatId = chatId;
            const res = await fetch(`api/chats/${chatId}/messages`);
            if (!res.ok) return;
            this.chatMessages = await res.json();
            // Restore provider/model/params from chat
            const chat = this.chatList.find(c => c.id === chatId);
            if (chat) {
                this.chatProvider = chat.provider || "ollama";
                this.chatModel = chat.model || "";
                if (chat.params) {
                    try { this.chatParams = { ...this.chatParams, ...JSON.parse(chat.params) }; } catch {}
                }
            }
            this.$nextTick(() => this.scrollChatToBottom());
        },

        async newChat() {
            this.abortChat();
            this.chatId = null;
            this.chatMessages = [];
        },

        async deleteChat(chatId) {
            await fetch(`api/chats/${chatId}`, { method: "DELETE" });
            if (this.chatId === chatId) {
                this.chatId = null;
                this.chatMessages = [];
            }
            await this.loadChats();
        },

        async sendChatMessage() {
            const message = this.chatInput.trim();
            if (!message || this.chatLoading || !this.selectedPaperId) return;

            this.abortChat();
            this.chatInput = "";
            this.chatMessages.push({ role: "user", content: message, id: Date.now() });
            this.chatLoading = true;
            this.chatStreamContent = "";
            this.$nextTick(() => this.scrollChatToBottom());

            this._chatAbortController = new AbortController();

            try {
                const res = await fetch(`api/papers/${this.selectedPaperId}/chat`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        message,
                        chat_id: this.chatId,
                        provider: this.chatProvider,
                        model: this.chatModel,
                        params: this.chatProvider === "ollama" ? this.chatParams : null,
                    }),
                    signal: this._chatAbortController.signal,
                });

                const reader = res.body.getReader();
                const decoder = new TextDecoder();

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    const chunk = decoder.decode(value, { stream: true });
                    const lines = chunk.split("\n");

                    for (const line of lines) {
                        if (!line.startsWith("data: ")) continue;
                        const data = JSON.parse(line.slice(6));

                        if (data.type === "chat_id") {
                            this.chatId = data.chat_id;
                        } else if (data.type === "text") {
                            this.chatStreamContent += data.text;
                            this.$nextTick(() => this.scrollChatToBottom());
                        } else if (data.type === "done") {
                            this.chatMessages.push({
                                role: "assistant",
                                content: this.chatStreamContent,
                                id: Date.now(),
                            });
                            this.chatStreamContent = "";
                            // Refresh chat list if this was a new chat
                            await this.loadChats();
                        } else if (data.type === "error") {
                            this.showToast(data.error, "error");
                        }
                    }
                }
            } catch (err) {
                if (err.name !== "AbortError") {
                    this.showToast("Chat failed: " + err.message, "error");
                }
            }
            this._chatAbortController = null;
            this.chatLoading = false;
        },

        scrollChatToBottom() {
            const container = this.$refs.chatMessages;
            if (container) container.scrollTop = container.scrollHeight;
        },

        scrollToPage(pageNum) {
            const pageDiv = document.querySelector(`.pdf-page[data-page="${pageNum}"]`);
            if (pageDiv) pageDiv.scrollIntoView({ behavior: "smooth", block: "center" });
        },

        scrollToPageAndHighlight(pageNum, quoteText) {
            this.scrollToPage(pageNum);
            // Small delay to let scroll complete, then highlight
            setTimeout(() => this.highlightTextOnPage(pageNum, quoteText), 300);
        },

        highlightTextOnPage(pageNum, quoteText) {
            // Clear any previous chat highlights
            document.querySelectorAll(".chat-text-highlight").forEach(el => el.remove());

            const pageDiv = document.querySelector(`.pdf-page[data-page="${pageNum}"]`);
            if (!pageDiv) return;

            const textLayer = pageDiv.querySelector(".textLayer");
            if (!textLayer) return;

            // Normalize the quote for matching (collapse whitespace)
            const normalizedQuote = quoteText.replace(/\s+/g, " ").trim().toLowerCase();
            if (!normalizedQuote) return;

            // Collect all text spans with their positions
            const spans = Array.from(textLayer.querySelectorAll("span"));
            const fullText = spans.map(s => s.textContent).join("");
            const normalizedFull = fullText.replace(/\s+/g, " ").toLowerCase();

            // Find the quote in the concatenated text
            const matchIdx = normalizedFull.indexOf(normalizedQuote);
            if (matchIdx === -1) return;

            // Map character index back to spans
            let charCount = 0;
            const matchSpans = [];
            for (const span of spans) {
                const normalizedSpan = span.textContent.replace(/\s+/g, " ");
                const spanStart = charCount;
                const spanEnd = charCount + normalizedSpan.length;
                charCount = spanEnd;

                if (spanEnd > matchIdx && spanStart < matchIdx + normalizedQuote.length) {
                    matchSpans.push(span);
                }
            }

            // Create highlight overlays on matched spans
            const overlay = pageDiv.querySelector(".pdf-annotation-layer");
            if (!overlay) return;

            for (const span of matchSpans) {
                const rect = span.getBoundingClientRect();
                const pageRect = pageDiv.getBoundingClientRect();
                const highlight = document.createElement("div");
                highlight.className = "chat-text-highlight";
                highlight.style.left = (rect.left - pageRect.left) + "px";
                highlight.style.top = (rect.top - pageRect.top) + "px";
                highlight.style.width = rect.width + "px";
                highlight.style.height = rect.height + "px";
                overlay.appendChild(highlight);
            }

            // Auto-remove after 4 seconds
            setTimeout(() => {
                document.querySelectorAll(".chat-text-highlight").forEach(el => {
                    el.style.transition = "opacity 0.5s";
                    el.style.opacity = "0";
                    setTimeout(() => el.remove(), 500);
                });
            }, 4000);
        },

        renderChatContent(content) {
            let html = this.escapeHtml(content);
            // Parse [[quote:"text" p.N]] into clickable blockquotes
            html = html.replace(/\[\[quote:&quot;(.*?)&quot;\s+p\.(\d+)\]\]/g, (match, text, page) => {
                const escaped = text.replace(/'/g, "\\'");
                return `<div class="chat-quote cursor-pointer" onclick="document.querySelector('[x-data]').__x.$data.scrollToPageAndHighlight(${page}, '${escaped}')"><span class="italic">&ldquo;${text}&rdquo;</span> <span class="badge badge-xs badge-primary">p.${page}</span></div>`;
            });
            // Parse [[p.N]] references into clickable badges
            html = html.replace(/\[\[p\.(\d+)\]\]/g,
                '<button class="badge badge-xs badge-primary cursor-pointer mx-0.5" onclick="document.querySelector(\'[data-page=\\\'$1\\\']\')?.scrollIntoView({behavior:\'smooth\',block:\'center\'})">p.$1</button>');
            // Basic markdown: bold, italic, code, code blocks
            html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="bg-base-300 rounded p-2 text-xs my-1 overflow-x-auto"><code>$2</code></pre>');
            html = html.replace(/`([^`]+)`/g, '<code class="bg-base-300 rounded px-1 text-xs">$1</code>');
            html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
            html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
            // Line breaks
            html = html.replace(/\n/g, '<br>');
            return html;
        },

        escapeHtml(text) {
            const div = document.createElement("div");
            div.textContent = text;
            return div.innerHTML;
        },

        // --- Toast ---

        showToast(msg, type = "info") {
            const id = ++this._toastCounter;
            this.toasts.push({ id, msg, type });
            setTimeout(() => {
                this.toasts = this.toasts.filter(t => t.id !== id);
            }, 3000);
        },
    }));
});
