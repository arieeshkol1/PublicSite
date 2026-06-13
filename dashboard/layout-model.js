/**
 * Layout Model Module
 * Dependency-free pure helpers for the single-layout dashboard model.
 * No DOM access, no network access — fully unit- and property-testable.
 *
 * Responsibilities:
 *  - Validate stored widget entries (isValidWidget)
 *  - Parse + classify a raw localStorage layout string (parseStoredLayout)
 *  - Build the canonical PUT /dashboard/layouts payload (buildSavePayload)
 */

const LayoutModel = (() => {
    const DEFAULT_LAYOUT_NAME = 'My Dashboard';

    function isFiniteNumber(value) {
        return typeof value === 'number' && Number.isFinite(value);
    }

    /**
     * A widget entry is valid for loading iff it has:
     *  - a `type` that is a non-empty string, and
     *  - a `gridPosition` object with numeric `x`, `y`, `w`, `h`.
     */
    function isValidWidget(widget) {
        if (!widget || typeof widget !== 'object') return false;

        if (typeof widget.type !== 'string' || widget.type.trim() === '') {
            return false;
        }

        const pos = widget.gridPosition;
        if (!pos || typeof pos !== 'object') return false;

        return (
            isFiniteNumber(pos.x) &&
            isFiniteNumber(pos.y) &&
            isFiniteNumber(pos.w) &&
            isFiniteNumber(pos.h)
        );
    }

    /**
     * Pure parse + classify of a raw localStorage string.
     * Returns one of:
     *   { status: 'empty' }        -> no value, or parsed layout with 0 widgets
     *   { status: 'unparseable' }  -> JSON.parse threw
     *   { status: 'ok', layout, validWidgets, omittedCount }
     */
    function parseStoredLayout(rawString) {
        // No stored value at all.
        if (rawString === null || rawString === undefined || rawString === '') {
            return { status: 'empty' };
        }

        let layout;
        try {
            layout = JSON.parse(rawString);
        } catch (e) {
            return { status: 'unparseable' };
        }

        // Parsed but not a usable layout object with a widgets array.
        if (!layout || typeof layout !== 'object' || !Array.isArray(layout.widgets)) {
            return { status: 'empty' };
        }

        if (layout.widgets.length === 0) {
            return { status: 'empty' };
        }

        const validWidgets = layout.widgets.filter(isValidWidget);
        const omittedCount = layout.widgets.length - validWidgets.length;

        return {
            status: 'ok',
            layout: layout,
            validWidgets: validWidgets,
            omittedCount: omittedCount
        };
    }

    /**
     * Builds the canonical save payload for the single Current_Layout.
     * `layout_id` is omitted (undefined) when no current id is set, so the
     * backend treats the first save as a create and subsequent saves as
     * updates targeting the same single layout.
     */
    function buildSavePayload(widgets, currentLayoutId) {
        return {
            layout_id: currentLayoutId || undefined,
            layout_name: DEFAULT_LAYOUT_NAME,
            widgets: widgets
        };
    }

    return {
        isValidWidget,
        parseStoredLayout,
        buildSavePayload,
        DEFAULT_LAYOUT_NAME
    };
})();

// CommonJS export guard so the pure helper can be imported by Node/jsdom tests
// without affecting browser usage (where it is a global from the <script> tag).
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LayoutModel;
}
