/**
 * 企微 JS-SDK 工具封装
 * 企微环境用 wx.chooseImage 拍照，非企微环境降级为 HTML input
 */

const isWecom = () => /wxwork/i.test(navigator.userAgent)

let wxReady = false
let wxConfigured = false

async function initWxConfig() {
  if (wxConfigured) return
  if (!isWecom()) return
  if (typeof wx === 'undefined') return

  try {
    const { getJsapiConfig } = await import('../api')
    const url = window.location.href.split('#')[0]
    const config = await getJsapiConfig(url)

    wx.config({
      beta: true,
      debug: false,
      appId: config.appId,
      timestamp: config.timestamp,
      nonceStr: config.nonceStr,
      signature: config.signature,
      jsApiList: ['chooseImage', 'getLocalImgData'],
    })

    await new Promise((resolve, reject) => {
      wx.ready(() => {
        wxReady = true
        resolve()
      })
      wx.error((err) => {
        console.warn('[wxsdk] wx.config 失败:', err)
        reject(err)
      })
    })
  } catch (e) {
    console.warn('[wxsdk] 初始化失败:', e)
  } finally {
    wxConfigured = true
  }
}

function chooseImageFromWx() {
  return new Promise((resolve, reject) => {
    wx.chooseImage({
      count: 1,
      sizeType: ['compressed'],
      sourceType: ['camera'],
      success: (res) => {
        const localId = res.localIds[0]
        wx.getLocalImgData({
          localId,
          success: (imgRes) => {
            const base64 = imgRes.localData
            // Android 返回的 base64 可能没有前缀，iOS 可能有多余换行
            const data = base64.replace(/\n/g, '')
            const mimeType = data.startsWith('data:') ? '' : 'data:image/jpeg;base64,'
            const fullBase64 = data.startsWith('data:') ? data : mimeType + data
            // 转为 File 对象
            const byteStr = atob(fullBase64.split(',')[1])
            const ab = new ArrayBuffer(byteStr.length)
            const ia = new Uint8Array(ab)
            for (let i = 0; i < byteStr.length; i++) {
              ia[i] = byteStr.charCodeAt(i)
            }
            const blob = new Blob([ab], { type: 'image/jpeg' })
            const file = new File([blob], 'camera.jpg', { type: 'image/jpeg' })
            resolve(file)
          },
          fail: reject,
        })
      },
      fail: reject,
    })
  })
}

/**
 * 统一拍照入口
 * 企微环境：wx.chooseImage
 * 非企微环境：触发隐藏的 input[type=file] 并返回 File
 */
export async function getPhoto() {
  if (isWecom() && wxReady) {
    return chooseImageFromWx()
  }
  // 降级：用 input[type=file] 让用户选择
  return new Promise((resolve, reject) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*'
    input.capture = 'camera'
    input.style.display = 'none'
    document.body.appendChild(input)
    input.onchange = () => {
      const file = input.files[0]
      document.body.removeChild(input)
      if (file) resolve(file)
      else reject(new Error('未选择图片'))
    }
    input.click()
  })
}

// 页面加载时初始化（延迟执行，不阻塞首屏）
if (isWecom()) {
  setTimeout(initWxConfig, 500)
}
