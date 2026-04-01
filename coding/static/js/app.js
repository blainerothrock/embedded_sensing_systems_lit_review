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
        view: "papers", // "papers" or "matrix"

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
        pdfPageCount: 0,
        pdfCurrentPage: 1,
        pdfRendering: false,

        // Coding state (v2: hierarchical codes on annotations)
        codes: [],              // top-level codes with children
        paperAnnotations: [],   // annotations for selected paper
        codingCompleteness: {},
        codeUsageCounts: {},    // {code_id: annotation_count}
        showCodeManager: false,
        newCodeName: "",
        newSubCodeNames: {},    // {parent_code_id: "name"}
        matrixData: null,
        paperMatrixCells: {},  // {code_id: {value, notes}} for selected paper

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
        toast: "",
        toastType: "info",
        toastTimeout: null,

        async init() {
            this.$watch("theme", (val) => {
                document.documentElement.setAttribute("data-theme", val);
            });
            document.documentElement.setAttribute("data-theme", this.theme);
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
            this.papers = await res.json();
        },

        async loadExclusionCodes() {
            const res = await fetch("api/exclusion-codes");
            this.exclusionCodes = await res.json();
        },

        async loadStats() {
            const res = await fetch("api/stats");
            this.stats = await res.json();
        },

        // --- Paper selection ---

        async selectPaper(id) {
            this.selectedPaperId = id;
            const res = await fetch(`api/papers/${id}`);
            this.selectedPaper = await res.json();

            // Populate review form
            this.reviewForm = {
                decision: this.selectedPaper.phase3_decision || null,
                notes: this.selectedPaper.phase3_notes || "",
                exclusion_code_ids: (this.selectedPaper.exclusion_codes || []).map(
                    (c) => c.id
                ),
            };

            // Load PDF if available
            if (this.selectedPaper.pdf_path) {
                await this.loadPdf(id);
            } else {
                this.clearPdf();
            }

            // Load annotations and matrix cells for this paper
            await Promise.all([
                this.loadPaperAnnotations(),
                this.loadPaperMatrixCells(),
            ]);
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
                await this.pdfFitWidth();
            } catch (err) {
                console.error("Failed to load PDF:", err);
                this.showToast("Failed to load PDF", "error");
            }
        },

        clearPdf() {
            const container = this.$refs?.pdfPages;
            if (container) container.innerHTML = "";
            _pdfDoc = null;
            this.pdfPageCount = 0;
            this.pdfCurrentPage = 1;
        },

        async renderAllPages() {
            if (!_pdfDoc || this.pdfRendering) return;
            this.pdfRendering = true;

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
                pageDiv.style.width = viewport.width + "px";
                pageDiv.style.height = viewport.height + "px";
                pageDiv.style.position = "relative";

                const canvas = document.createElement("canvas");
                canvas.width = viewport.width * window.devicePixelRatio;
                canvas.height = viewport.height * window.devicePixelRatio;
                canvas.style.width = viewport.width + "px";
                canvas.style.height = viewport.height + "px";

                const ctx = canvas.getContext("2d");
                ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

                pageDiv.appendChild(canvas);
                container.appendChild(pageDiv);

                await page.render({
                    canvasContext: ctx,
                    viewport: viewport,
                }).promise;

                // Text layer for selection (PDF.js v5 requires CSS custom properties)
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
            }

            // Render existing annotations
            this.renderAnnotationOverlays();
            this.pdfRendering = false;
        },

        // --- Annotation overlay rendering ---

        renderAnnotationOverlays() {
            // Clear existing overlays
            document.querySelectorAll(".pdf-annotation-layer").forEach(
                (el) => (el.innerHTML = "")
            );

            for (const ann of this.paperAnnotations) {
                const rects = JSON.parse(ann.rects_json || "[]");
                const color = ann.codes?.[0]?.color || "#FFEB3B";
                const isArea = ann.annotation_type === "area";

                for (const rect of rects) {
                    // Each rect may have its own page, or default to annotation's page
                    const pageNum = rect.page || ann.page_number;
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

        onPdfWheel(event) {
            const container = this.$refs.pdfContainer;
            if (!container || !_pdfDoc) return;

            const delta = event.deltaY > 0 ? -0.1 : 0.1;
            const oldScale = this.pdfScale;
            const newScale = Math.min(Math.max(oldScale + delta, 0.5), 4.0);
            if (newScale === oldScale) return;

            // On first tick of a zoom gesture, capture the anchor point
            // in PDF-content space (independent of scale)
            if (!_zoomAnchor) {
                const rect = container.getBoundingClientRect();
                const cursorX = event.clientX - rect.left;
                const cursorY = event.clientY - rect.top;
                _zoomAnchor = {
                    // Content-space point = scroll + cursor, normalized by scale
                    contentX: (container.scrollLeft + cursorX) / oldScale,
                    contentY: (container.scrollTop + cursorY) / oldScale,
                    cursorX,
                    cursorY,
                };
            }

            this.pdfScale = newScale;

            // Debounce re-render
            clearTimeout(_zoomRenderTimer);
            _zoomRenderTimer = setTimeout(async () => {
                const anchor = _zoomAnchor;
                _zoomAnchor = null;
                await this.renderAllPages();
                if (anchor) {
                    container.scrollLeft = anchor.contentX * this.pdfScale - anchor.cursorX;
                    container.scrollTop = anchor.contentY * this.pdfScale - anchor.cursorY;
                }
            }, 100);
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

        async pdfZoomIn() {
            this.pdfScale = Math.min(this.pdfScale + 0.25, 4.0);

            await this.renderAllPages();
        },

        async pdfZoomOut() {
            this.pdfScale = Math.max(this.pdfScale - 0.25, 0.5);

            await this.renderAllPages();
        },

        async pdfFitWidth() {
            if (!_pdfDoc) return;
            const page = await _pdfDoc.getPage(1);
            const container = this.$refs.pdfContainer;
            const containerWidth = container.clientWidth - 40; // padding
            const viewport = page.getViewport({ scale: 1.0 });
            this.pdfScale = containerWidth / viewport.width;

            await this.renderAllPages();
        },

        onPdfScroll() {
            // Update current page based on scroll position
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

        // --- Matrix ---

        async loadCodingCompleteness() {
            const res = await fetch("api/coding/completeness");
            this.codingCompleteness = await res.json();
        },

        async loadMatrix() {
            const res = await fetch("api/matrix");
            this.matrixData = await res.json();
        },

        async saveMatrixCell(docId, codeId, value) {
            await fetch("api/matrix/cell", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ document_id: docId, code_id: codeId, value }),
            });
            // Update local state
            if (!this.matrixData.cells[docId]) this.matrixData.cells[docId] = {};
            this.matrixData.cells[docId][codeId] = { value, notes: null };
        },

        async loadPaperMatrixCells() {
            if (!this.selectedPaperId) return;
            const res = await fetch(`api/papers/${this.selectedPaperId}/matrix-cells`);
            this.paperMatrixCells = await res.json();
        },

        async savePaperMatrixCell(codeId, value) {
            await fetch("api/matrix/cell", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ document_id: this.selectedPaperId, code_id: codeId, value }),
            });
            if (!this.paperMatrixCells[codeId]) this.paperMatrixCells[codeId] = {};
            this.paperMatrixCells[codeId].value = value;
        },

        getEvidenceForCode(code) {
            const codeIds = new Set([code.id, ...(code.children || []).map(c => c.id)]);
            return this.paperAnnotations.filter(ann =>
                ann.codes.some(c => codeIds.has(c.id))
            );
        },

        // --- Toast ---

        showToast(msg, type = "info") {
            this.toast = msg;
            this.toastType = type;
            clearTimeout(this.toastTimeout);
            this.toastTimeout = setTimeout(() => {
                this.toast = "";
            }, 3000);
        },
    }));
});
