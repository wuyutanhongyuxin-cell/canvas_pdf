// ==UserScript==
// @name         交大课件高清PDF下载器
// @namespace    https://v.sjtu.edu.cn/
// @version      2.0.0
// @description  一键提取交大课程平台课件，通过本地服务自动下载原图并合成高清 PDF
// @author       dsy
// @match        https://*.sjtu.edu.cn/*
// @match        http://*.sjtu.edu.cn/*
// @grant        GM_xmlhttpRequest
// @grant        GM_addStyle
// @grant        window.onurlchange
// @connect      self
// @connect      127.0.0.1
// @connect      localhost
// @connect      s3.jcloud.sjtu.edu.cn
// @connect      *
// @run-at       document-body
// ==/UserScript==

(function () {
  'use strict';

  const BUTTON_IDLE_TEXT = '📄 下载高清 PDF';
  const BUTTON_BUSY_TEXT = '⏳ 处理中...';
  const DEFAULT_FILE_NAME = '课件';
  const LOCAL_SERVICE_URL = 'http://127.0.0.1:38765';
  const WAIT_TIMEOUT_MS = 15000;
  const IMAGE_TIMEOUT_MS = 20000;
  const THUMBNAIL_SETTLE_MS = 7000;
  const STABLE_ROUNDS = 3;
  const PAGE_MARKER_SELECTORS = [
    '.ppt-card-wrapper__inner',
    '.ppt-card-wrapper',
    '[class*="ppt-card-wrapper__inner"]',
    '[class*="ppt-card-wrapper"]',
    'input[placeholder*="PPT"]',
  ];
  const CONTAINER_SELECTORS = [
    '.ppt-card-wrapper__inner',
    '.ppt-card-wrapper',
    '[class*="ppt-card-wrapper__inner"]',
    '[class*="ppt-card-wrapper"]',
    '[class*="ppt-card"]',
  ];
  const TITLE_SELECTORS = ['.course-title', '.title', 'h1', 'h2'];

  const ui = {
    btn: null,
    toast: null,
  };
  let pageCheckTimer = null;
  let bootstrappedUrl = '';

  const testHooks = globalThis.__SJTU_SLIDE_DOWNLOADER_TEST__;

  GM_addStyle(`
    #sjtu-pdf-btn {
      position: fixed;
      bottom: 30px;
      right: 30px;
      z-index: 99999;
      padding: 12px 20px;
      background: #1a56db;
      color: #fff;
      border: none;
      border-radius: 8px;
      font-size: 14px;
      font-weight: bold;
      cursor: pointer;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      transition: background 0.2s;
    }
    #sjtu-pdf-btn:hover { background: #1e40af; }
    #sjtu-pdf-btn:disabled { background: #6b7280; cursor: not-allowed; }

    #sjtu-pdf-toast {
      position: fixed;
      bottom: 90px;
      right: 30px;
      z-index: 99999;
      padding: 10px 16px;
      background: rgba(0,0,0,0.78);
      color: #fff;
      border-radius: 6px;
      font-size: 13px;
      display: none;
      max-width: 360px;
      line-height: 1.5;
      white-space: pre-wrap;
    }
  `);

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  function sanitizeFilename(raw) {
    const normalized = String(raw || '')
      .replace(/[\\/:*?"<>|]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();

    return (normalized || DEFAULT_FILE_NAME).slice(0, 80);
  }

  function showToast(message) {
    if (!ui.toast) {
      return;
    }
    ui.toast.textContent = message;
    ui.toast.style.display = 'block';
  }

  function hideToast() {
    if (!ui.toast) {
      return;
    }
    ui.toast.style.display = 'none';
  }

  function setButtonBusy(isBusy) {
    if (!ui.btn) {
      return;
    }
    ui.btn.disabled = isBusy;
    ui.btn.textContent = isBusy ? BUTTON_BUSY_TEXT : BUTTON_IDLE_TEXT;
  }

  function logDebug(message, extra) {
    if (typeof extra === 'undefined') {
      console.info(`[sjtu-pdf] ${message}`);
      return;
    }
    console.info(`[sjtu-pdf] ${message}`, extra);
  }

  function requestJson(details) {
    return new Promise((resolve, reject) => {
      GM_xmlhttpRequest({
        ...details,
        onload: (response) => {
          try {
            const rawText = typeof response.responseText === 'string'
              ? response.responseText
              : '';
            const payload = rawText ? JSON.parse(rawText) : null;
            resolve({ response, payload });
          } catch (error) {
            reject(new Error(`JSON 解析失败: ${error.message}`));
          }
        },
        onerror: () => reject(new Error(`请求失败: ${details.url}`)),
        ontimeout: () => reject(new Error(`请求超时: ${details.url}`)),
      });
    });
  }

  function getCourseTitle() {
    for (const selector of TITLE_SELECTORS) {
      const el = document.querySelector(selector);
      const text = el && el.textContent ? el.textContent.trim() : '';
      if (text) {
        return sanitizeFilename(text);
      }
    }
    return DEFAULT_FILE_NAME;
  }

  function waitFor(getter, label, timeout = WAIT_TIMEOUT_MS) {
    return new Promise((resolve, reject) => {
      const existing = getter();
      if (existing) {
        resolve(existing);
        return;
      }

      const observer = new MutationObserver(() => {
        const found = getter();
        if (found) {
          cleanup();
          resolve(found);
        }
      });

      const timer = setTimeout(() => {
        cleanup();
        reject(new Error(`等待超时: ${label}`));
      }, timeout);

      function cleanup() {
        clearTimeout(timer);
        observer.disconnect();
      }

      const root = document.documentElement || document.body;
      if (!root) {
        cleanup();
        reject(new Error('页面尚未完成初始化'));
        return;
      }

      observer.observe(root, { childList: true, subtree: true });
    });
  }

  function collectCandidateContainers() {
    const results = [];
    const seen = new Set();

    for (const selector of CONTAINER_SELECTORS) {
      const nodes = Array.from(document.querySelectorAll(selector));
      for (const node of nodes) {
        if (!node || seen.has(node)) {
          continue;
        }
        seen.add(node);
        results.push(node);
      }
    }

    if (!results.length) {
      const fallbackNodes = Array.from(document.querySelectorAll('div, section, ul'));
      for (const node of fallbackNodes) {
        if (!node || seen.has(node) || typeof node.querySelectorAll !== 'function') {
          continue;
        }
        const imgCount = node.querySelectorAll('img').length;
        if (imgCount >= 3) {
          seen.add(node);
          results.push(node);
        }
      }
    }

    return results;
  }

  function scoreContainer(node) {
    const imgCount = node.querySelectorAll('img').length;
    const childCount = node.children ? node.children.length : 0;
    const scrollableScore = node.scrollWidth > node.clientWidth ? 50 : 0;
    return scrollableScore + (imgCount * 10) + childCount;
  }

  function findBestSlideContainer() {
    const candidates = collectCandidateContainers()
      .filter(node => node && typeof node.querySelectorAll === 'function')
      .sort((left, right) => scoreContainer(right) - scoreContainer(left));

    return candidates[0] || null;
  }

  function isLikelyCoursePage() {
    const hostname = (location.hostname || '').toLowerCase();
    if (!hostname.endsWith('.sjtu.edu.cn') && hostname !== 'sjtu.edu.cn') {
      return false;
    }

    if (findBestSlideContainer()) {
      return true;
    }

    for (const selector of PAGE_MARKER_SELECTORS) {
      if (document.querySelector(selector)) {
        return true;
      }
    }

    return false;
  }

  function normalizeUrl(rawUrl) {
    if (!rawUrl) {
      return null;
    }

    const value = String(rawUrl).trim();
    if (!value) {
      return null;
    }

    if (value.startsWith('data:image/') || value.startsWith('blob:')) {
      return value;
    }

    try {
      return new URL(value, location.href).href;
    } catch (error) {
      return null;
    }
  }

  function isUsableImageUrl(url) {
    if (!url) {
      return false;
    }

    if (url.startsWith('data:image/') || url.startsWith('blob:')) {
      return true;
    }

    if (!/^https?:/i.test(url)) {
      return false;
    }

    return !/placeholder|blank|loading|spinner/i.test(url);
  }

  function getImageCandidateUrl(img) {
    const dataset = img.dataset || {};
    const candidates = [
      img.currentSrc,
      img.src,
      typeof img.getAttribute === 'function' ? img.getAttribute('src') : null,
      dataset.src,
      dataset.original,
      dataset.lazySrc,
      dataset.lazyload,
      dataset.url,
      typeof img.getAttribute === 'function' ? img.getAttribute('data-src') : null,
      typeof img.getAttribute === 'function' ? img.getAttribute('data-original') : null,
      typeof img.getAttribute === 'function' ? img.getAttribute('data-url') : null,
    ];

    for (const candidate of candidates) {
      const normalized = normalizeUrl(candidate);
      if (isUsableImageUrl(normalized)) {
        return normalized;
      }
    }

    return null;
  }

  function collectSlideImageUrls(container) {
    const urls = [];
    const seen = new Set();
    const images = Array.from(container.querySelectorAll('img'));

    for (const img of images) {
      const url = getImageCandidateUrl(img);
      if (!url || seen.has(url)) {
        continue;
      }
      seen.add(url);
      urls.push(url);
    }

    return urls;
  }

  async function waitForThumbnailSettle(container, timeout = THUMBNAIL_SETTLE_MS) {
    const deadline = Date.now() + timeout;
    let stableRounds = 0;
    let previousSignature = '';

    while (Date.now() < deadline) {
      const urls = collectSlideImageUrls(container);
      const images = Array.from(container.querySelectorAll('img'));
      const pendingImages = images.some(img => {
        const candidate = getImageCandidateUrl(img);
        return candidate && !img.complete;
      });
      const signature = `${urls.join('|')}::${pendingImages}`;

      if (signature === previousSignature) {
        stableRounds += 1;
        if (stableRounds >= STABLE_ROUNDS) {
          return urls;
        }
      } else {
        stableRounds = 0;
        previousSignature = signature;
      }

      await sleep(250);
    }

    return collectSlideImageUrls(container);
  }

  async function scrollToLoadAll(container) {
    const step = Math.max(container.clientWidth || 400, 240);
    let previousSignature = '';
    let stableRounds = 0;

    container.scrollLeft = 0;

    for (let pass = 0; pass < 80; pass += 1) {
      const nextScrollLeft = Math.min(
        container.scrollLeft + step,
        Math.max(container.scrollWidth - container.clientWidth, 0),
      );

      container.scrollLeft = nextScrollLeft;
      await sleep(250);

      const urls = collectSlideImageUrls(container);
      const atEnd = container.scrollLeft + container.clientWidth >= container.scrollWidth - 2;
      const signature = `${container.scrollLeft}|${urls.length}|${urls.join('|')}`;

      if (signature === previousSignature && atEnd) {
        stableRounds += 1;
        if (stableRounds >= STABLE_ROUNDS) {
          break;
        }
      } else {
        stableRounds = 0;
        previousSignature = signature;
      }

      if (!atEnd) {
        continue;
      }
    }

    const urls = await waitForThumbnailSettle(container);
    container.scrollLeft = 0;
    return urls;
  }

  function getPageOrientation(width, height) {
    return width >= height ? 'landscape' : 'portrait';
  }

  function guessImageFormat(mimeType, url) {
    const source = `${mimeType || ''} ${url || ''}`.toLowerCase();
    if (source.includes('png')) {
      return 'PNG';
    }
    if (source.includes('webp')) {
      return 'WEBP';
    }
    if (source.includes('jpg') || source.includes('jpeg')) {
      return 'JPEG';
    }
    return undefined;
  }

  function waitForImageLoad(img) {
    return new Promise((resolve, reject) => {
      if (img.complete && img.naturalWidth > 0 && img.naturalHeight > 0) {
        resolve(img);
        return;
      }

      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error('图片加载失败'));
    });
  }

  async function loadImageFromSrc(src) {
    const img = new Image();
    img.decoding = 'async';
    const loadTask = waitForImageLoad(img);
    img.src = src;
    await loadTask;

    if (typeof img.decode === 'function') {
      await img.decode().catch(() => undefined);
    }

    const width = img.naturalWidth || img.width;
    const height = img.naturalHeight || img.height;
    if (!width || !height) {
      throw new Error('图片尺寸无效');
    }

    return { image: img, width, height };
  }

  function fetchImageBlob(url) {
    return new Promise((resolve, reject) => {
      GM_xmlhttpRequest({
        method: 'GET',
        url,
        responseType: 'blob',
        timeout: IMAGE_TIMEOUT_MS,
        onload: (response) => {
          if (response.status < 200 || response.status >= 300 || !response.response) {
            reject(new Error(`请求失败 (${response.status || 'unknown'}): ${url}`));
            return;
          }
          resolve({
            blob: response.response,
            finalUrl: response.finalUrl || url,
          });
        },
        onerror: () => reject(new Error(`请求失败: ${url}`)),
        ontimeout: () => reject(new Error(`请求超时: ${url}`)),
      });
    });
  }

  async function fetchRenderableImage(url) {
    if (url.startsWith('data:image/') || url.startsWith('blob:')) {
      const loaded = await loadImageFromSrc(url);
      return {
        ...loaded,
        format: guessImageFormat('', url),
        cleanup() {},
      };
    }

    const { blob, finalUrl } = await fetchImageBlob(url);
    const objectUrl = URL.createObjectURL(blob);

    try {
      const loaded = await loadImageFromSrc(objectUrl);
      return {
        ...loaded,
        format: guessImageFormat(blob.type, finalUrl),
        cleanup() {
          URL.revokeObjectURL(objectUrl);
        },
      };
    } catch (error) {
      URL.revokeObjectURL(objectUrl);
      throw error;
    }
  }

  async function checkLocalService() {
    const { response, payload } = await requestJson({
      method: 'GET',
      url: `${LOCAL_SERVICE_URL}/health`,
      timeout: 5000,
    });

    if (response.status < 200 || response.status >= 300 || !payload || !payload.ok) {
      throw new Error('本地高清 PDF 服务未就绪');
    }

    return payload;
  }

  async function sendJobToLocalService(payload) {
    const { response, payload: result } = await requestJson({
      method: 'POST',
      url: `${LOCAL_SERVICE_URL}/jobs`,
      headers: {
        'Content-Type': 'application/json',
      },
      data: JSON.stringify(payload),
      timeout: 60 * 1000,
    });

    if (response.status < 200 || response.status >= 300 || !result || !result.ok) {
      throw new Error((result && result.error) || '本地服务处理失败');
    }

    return result;
  }

  function ensureJsPdf() {
    const jspdfNamespace = window.jspdf;
    if (!jspdfNamespace || typeof jspdfNamespace.jsPDF !== 'function') {
      throw new Error('jsPDF 未成功加载，请刷新页面后重试');
    }
    return jspdfNamespace.jsPDF;
  }

  async function generatePDF(imgUrls, title) {
    const jsPDF = ensureJsPdf();
    let pdf = null;
    let successCount = 0;
    const failedPages = [];

    for (let index = 0; index < imgUrls.length; index += 1) {
      const pageNumber = index + 1;
      showToast(`正在处理第 ${pageNumber} / ${imgUrls.length} 页...`);

      let asset = null;
      try {
        asset = await fetchRenderableImage(imgUrls[index]);
        const pageFormat = [asset.width, asset.height];
        const pageOrientation = getPageOrientation(asset.width, asset.height);

        if (!pdf) {
          pdf = new jsPDF({
            orientation: pageOrientation,
            unit: 'px',
            format: pageFormat,
            hotfixes: ['px_scaling'],
            compress: true,
          });
        } else {
          pdf.addPage(pageFormat, pageOrientation);
        }

        pdf.addImage(
          asset.image,
          asset.format,
          0,
          0,
          asset.width,
          asset.height,
          undefined,
          'FAST',
        );
        successCount += 1;
      } catch (error) {
        failedPages.push({ pageNumber, url: imgUrls[index], error: error.message });
        console.warn(`第 ${pageNumber} 页处理失败`, error);
      } finally {
        if (asset) {
          asset.cleanup();
        }
      }
    }

    if (!pdf || successCount === 0) {
      throw new Error('所有页面都下载失败，未生成 PDF');
    }

    pdf.save(`${sanitizeFilename(title)}.pdf`);
    return {
      successCount,
      failureCount: failedPages.length,
      failedPages,
    };
  }

  async function handleDownload() {
    setButtonBusy(true);

    try {
      showToast('正在检查本地高清 PDF 服务...');
      await checkLocalService();

      showToast('正在查找课件区域...');
      const container = await waitFor(findBestSlideContainer, '课件缩略图容器');

      const cardCount = container.children ? container.children.length : 0;
      if (cardCount === 0) {
        throw new Error('未找到课件条目，请确认页面已加载完成');
      }

      showToast(`检测到 ${cardCount} 个条目，正在加载缩略图...`);
      const imageUrls = await scrollToLoadAll(container);

      if (!imageUrls.length) {
        throw new Error('未找到可下载的课件图片，请先手动展开或滚动课件区域后再试');
      }

      showToast(`找到 ${imageUrls.length} 张图片，正在提交到本地高清服务...`);
      const title = getCourseTitle();
      const result = await sendJobToLocalService({
        title,
        sourceUrl: location.href,
        imageUrls,
      });

      showToast(`✅ 高清 PDF 已生成\n页数 ${result.page_count}\n保存位置 ${result.pdf_path}`);

      setTimeout(hideToast, 5000);
      return result;
    } catch (error) {
      const help = error.message.includes('127.0.0.1')
        ? '\n请先运行: python local_pdf_service.py'
        : '';
      showToast(`❌ 出错: ${error.message}${help}`);
      console.error(error);
      throw error;
    } finally {
      setButtonBusy(false);
    }
  }

  function createUi() {
    if (!document.body || ui.btn || document.getElementById('sjtu-pdf-btn')) {
      return;
    }

    const btn = document.createElement('button');
    btn.id = 'sjtu-pdf-btn';
    btn.textContent = BUTTON_IDLE_TEXT;
    btn.addEventListener('click', () => {
      handleDownload().catch(() => undefined);
    });
    document.body.appendChild(btn);

    const toast = document.createElement('div');
    toast.id = 'sjtu-pdf-toast';
    document.body.appendChild(toast);

    ui.btn = btn;
    ui.toast = toast;
    logDebug('UI injected', { href: location.href });
  }

  function removeUi() {
    if (ui.btn && typeof ui.btn.remove === 'function') {
      ui.btn.remove();
    }
    if (ui.toast && typeof ui.toast.remove === 'function') {
      ui.toast.remove();
    }
    ui.btn = null;
    ui.toast = null;
  }

  function syncUiToPage() {
    const matched = isLikelyCoursePage();
    if (matched) {
      createUi();
      return true;
    }

    if (ui.btn || ui.toast) {
      logDebug('Target markers disappeared, removing UI', { href: location.href });
      removeUi();
    }

    return false;
  }

  function schedulePageCheck(reason, delay = 300) {
    clearTimeout(pageCheckTimer);
    pageCheckTimer = setTimeout(() => {
      pageCheckTimer = null;
      const currentUrl = location.href;
      const changed = currentUrl !== bootstrappedUrl;
      bootstrappedUrl = currentUrl;
      logDebug(`Running page check: ${reason}`, { href: currentUrl, changed });
      syncUiToPage();
    }, delay);
  }

  function installSpaListeners() {
    if ('onurlchange' in window) {
      window.addEventListener('urlchange', () => {
        schedulePageCheck('urlchange', 250);
      });
      logDebug('Registered window.onurlchange listener');
    }

    const historyObject = window.history;
    if (!historyObject || historyObject.__sjtuPdfPatched) {
      return;
    }

    for (const methodName of ['pushState', 'replaceState']) {
      const original = historyObject[methodName];
      if (typeof original !== 'function') {
        continue;
      }

      historyObject[methodName] = function (...args) {
        const result = original.apply(this, args);
        schedulePageCheck(`history.${methodName}`, 150);
        return result;
      };
    }

    historyObject.__sjtuPdfPatched = true;
    window.addEventListener('popstate', () => {
      schedulePageCheck('popstate', 150);
    });
    logDebug('Registered history listeners fallback');
  }

  function bootstrap() {
    if (testHooks && testHooks.disableBootstrap) {
      return;
    }

    installSpaListeners();

    if (document.body) {
      schedulePageCheck('initial-body', 0);
    }

    const start = () => {
      waitFor(() => (syncUiToPage() ? document.body : null), '交大课件页面', 60000)
        .then(() => {
          bootstrappedUrl = location.href;
        })
        .catch(() => undefined);
    };

    if (document.readyState === 'loading') {
      window.addEventListener('DOMContentLoaded', start, { once: true });
      return;
    }

    start();
  }

  if (testHooks) {
    Object.assign(testHooks, {
      sanitizeFilename,
      normalizeUrl,
      isUsableImageUrl,
      getImageCandidateUrl,
      collectSlideImageUrls,
      guessImageFormat,
      getPageOrientation,
      generatePDF,
      scrollToLoadAll,
      waitForThumbnailSettle,
      findBestSlideContainer,
      isLikelyCoursePage,
      checkLocalService,
      sendJobToLocalService,
      handleDownload,
    });
  }

  bootstrap();
})();
