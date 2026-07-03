// Shared enum option arrays for plating zone (镀银区域) and surface treatment (表面处理).
//
// Extracted from Camera.vue / StockIn.vue / InventoryEdit.vue / InventoryGroupedEdit.vue
// (form variant) and InventoryList.vue (filter variant) to remove cross-file duplication.
//
// Static data only — no behavior, no reactivity. Each consuming component keeps its own
// showXxxPicker refs and onXxxConfirm handlers because those reference component-local state.
//
// IMPORTANT: option entries use Vant's { text, value } object form (NOT plain string arrays).

// Core enum values — single source of truth.
const PLATING_VALUES = ['单环镀', '双环镀', '局部镀银']
const SURFACE_VALUES = ['CRC', 'SRC', 'ERC']

// Form variant: option lists END with a "无" (none / clear) entry.
// Used by Camera.vue, StockIn.vue, InventoryEdit.vue, InventoryGroupedEdit.vue.
export const platingOptions = [
  ...PLATING_VALUES.map(v => ({ text: v, value: v })),
  { text: '无', value: '' },
]

export const surfaceOptions = [
  ...SURFACE_VALUES.map(v => ({ text: v, value: v })),
  { text: '无', value: '' },
]

// Filter variant: option lists START with a "全部" (all) entry, no "无".
// Used by InventoryList.vue for the search filter chips.
export const platingFilterOptions = [
  { text: '全部', value: '' },
  ...PLATING_VALUES.map(v => ({ text: v, value: v })),
]

export const surfaceFilterOptions = [
  { text: '全部', value: '' },
  ...SURFACE_VALUES.map(v => ({ text: v, value: v })),
]
