/**
 * 企微 JS-SDK 工具封装
 * 企微环境用 wx.chooseImage 拍照，非企微环境降级为 HTML input
 */

const isWecom = () => /wxwork/i.test(navigator.userAgent)

/**
 * 压缩并转灰度图：最大宽度 500px，JPEG 质量 0.5
 * 先转为灰度再编码，省掉色度通道，JPEG 体积约再减 30%
 */
function compressImage(file) {
  return new Promise((resolve) => {
    const MAX_WIDTH = 500
    const QUALITY = 0.5
    const img = new Image()
    const url = URL.createObjectURL(file)
    img.onload = () => {
      URL.revokeObjectURL(url)
      if (img.width <= MAX_WIDTH && file.size < 300 * 1024) {
        resolve(file)
        return
      }
      const scale = Math.min(1, MAX_WIDTH / img.width)
      const canvas = document.createElement('canvas')
      canvas.width = Math.round(img.width * scale)
      canvas.height = Math.round(img.height * scale)
      const ctx = canvas.getContext('2d')
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height)

      // 转灰度：OCR 不需要颜色信息，去掉色度通道可压缩更小
      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height)
      const pixels = imageData.data
      for (let i = 0; i < pixels.length; i += 4) {
        const gray = 0.299 * pixels[i] + 0.587 * pixels[i + 1] + 0.114 * pixels[i + 2]
        pixels[i] = pixels[i + 1] = pixels[i + 2] = gray
      }
      ctx.putImageData(imageData, 0, 0)

      canvas.toBlob(
        (blob) => {
          resolve(new File([blob], file.name.replace(/\.\w+$/, '.jpg'), { type: 'image/jpeg' }))
        },
        'image/jpeg',
        QUALITY,
      )
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      resolve(file)
    }
    img.src = url
  })
}

let wxReady = false
let wxConfigured = false
let wxInitAttempts = 0
const WX_MAX_RETRIES = 3

async function initWxConfig() {
  if (wxConfigured) return
  if (wxInitAttempts >= WX_MAX_RETRIES) return
  if (!isWecom()) return
  if (typeof wx === 'undefined') return

  wxInitAttempts++
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
    wxConfigured = true
  } catch (e) {
    console.warn('[wxsdk] 初始化失败:', e)
  }
}

function chooseImageFromWx(sourceType) {
  return new Promise((resolve, reject) => {
    wx.chooseImage({
      count: 1,
      sizeType: ['compressed'],
      sourceType: [sourceType],
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
 * 获取图片（指定来源）
 * @param {'camera'|'album'} source - camera 拍照，album 从相册选择
 */
export async function getPhoto(source = 'camera') {
  let file
  if (isWecom() && wxReady) {
    file = await chooseImageFromWx(source)
  } else {
    file = await new Promise((resolve, reject) => {
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = 'image/*'
      if (source === 'camera') input.capture = 'camera'
      input.style.display = 'none'
      document.body.appendChild(input)
      input.onchange = () => {
        const f = input.files[0]
        document.body.removeChild(input)
        if (f) resolve(f)
        else reject(new Error('未选择图片'))
      }
      input.click()
    })
  }
  return compressImage(file)
}

// 页面加载时初始化（延迟执行，不阻塞首屏）
if (isWecom()) {
  setTimeout(initWxConfig, 500)
}
