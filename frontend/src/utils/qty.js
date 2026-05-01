/**
 * 将数量字符串解析为数值（系统所有数量以 K 为单位存储）
 *   "46.368" → 46.368（K 值）
 *   "46.368K" → 46.368（忽略 K 后缀，因为已是 K 单位）
 */
export function parseQtyToK(val) {
  if (typeof val === 'number') return val
  const s = String(val).trim()
  // 提取数字部分，忽略 K/M 等后缀（系统以 K 为单位，后缀只是显示用）
  const m = s.match(/([\d.]+)/)
  return m ? parseFloat(m[1]) : 0
}

/**
 * 判断库存是否低于阈值（K 单位比较）
 * @param {string|number} quantity 库存数量（K 单位值）
 * @param {number} thresholdK 阈值，默认 2（即 2K）
 */
export function isLowStock(quantity, thresholdK = 2) {
  return parseQtyToK(quantity) < thresholdK
}
