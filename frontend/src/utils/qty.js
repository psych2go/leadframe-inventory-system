/**
 * 将数量字符串解析为 K 单位的数值
 * 与后端 _qty_to_num 保持一致：
 *   "46.368" → 46.368（纯数字即 K 值）
 *   "46.368K" → 46368（有 K 后缀则乘以 1000）
 *   "5M" → 5000000
 */
export function parseQtyToK(val) {
  if (typeof val === 'number') return val
  const s = String(val).trim()
  const kMatch = s.match(/([\d.]+)\s*[Kk]/)
  if (kMatch) return parseFloat(kMatch[1]) * 1000
  const mMatch = s.match(/([\d.]+)\s*[Mm]/)
  if (mMatch) return parseFloat(mMatch[1]) * 1000000
  const numMatch = s.match(/([\d.]+)/)
  return numMatch ? parseFloat(numMatch[1]) : 0
}

/**
 * 判断库存是否低于阈值（K 单位比较）
 * @param {string|number} quantity 库存数量（K 单位值）
 * @param {number} thresholdK 阈值，默认 2（即 2K）
 */
export function isLowStock(quantity, thresholdK = 2) {
  return parseQtyToK(quantity) < thresholdK
}
