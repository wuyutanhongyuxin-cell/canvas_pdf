const fs = require('fs');
const path = require('path');
const vm = require('vm');

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

class FakeElement {
  constructor(tagName) {
    this.tagName = String(tagName || 'div').toUpperCase();
    this.children = [];
    this.style = {};
    this.dataset = {};
    this.attributes = {};
    this.eventListeners = {};
    this.textContent = '';
    this.id = '';
    this.src = '';
    this.currentSrc = '';
    this.complete = true;
    this.scrollLeft = 0;
    this.scrollWidth = 0;
    this.clientWidth = 0;
    this._images = [];
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  remove() {
    return undefined;
  }

  addEventListener(type, listener) {
    this.eventListeners[type] = listener;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name === 'id') {
      this.id = String(value);
    }
  }

  getAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this.attributes, name)
      ? this.attributes[name]
      : null;
  }

  querySelectorAll(selector) {
    if (selector === 'img') {
      return this._images.slice();
    }
    return [];
  }
}

class FakeDocument {
  constructor() {
    this.body = new FakeElement('body');
    this.documentElement = new FakeElement('html');
    this.singleResults = new Map();
    this.multiResults = new Map();
  }

  createElement(tagName) {
    return new FakeElement(tagName);
  }

  getElementById(id) {
    return this.body.children.find(child => child.id === id) || null;
  }

  querySelector(selector) {
    const list = this.multiResults.get(selector);
    if (list && list.length) {
      return list[0];
    }
    return this.singleResults.get(selector) || null;
  }

  querySelectorAll(selector) {
    return (this.multiResults.get(selector) || []).slice();
  }

  setQuerySelector(selector, element) {
    this.singleResults.set(selector, element);
  }

  setQuerySelectorAll(selector, elements) {
    this.multiResults.set(selector, elements.slice());
  }
}

function createSandbox(options = {}) {
  const document = new FakeDocument();
  const objectUrlMap = new Map();
  const gmResponses = new Map();
  const pdfInstances = [];

  class FakeImage {
    constructor() {
      this.onload = null;
      this.onerror = null;
      this.complete = false;
      this.naturalWidth = 0;
      this.naturalHeight = 0;
      this.decoding = 'auto';
      this._src = '';
    }

    set src(value) {
      this._src = value;
      const payload = objectUrlMap.get(value) || (String(value).startsWith('data:image/')
        ? { width: 800, height: 600, type: 'image/png' }
        : null);

      if (!payload) {
        this.complete = false;
        setImmediate(() => {
          if (typeof this.onerror === 'function') {
            this.onerror(new Error(`Unknown image source: ${value}`));
          }
        });
        return;
      }

      this.complete = true;
      this.naturalWidth = payload.width;
      this.naturalHeight = payload.height;
      setImmediate(() => {
        if (typeof this.onload === 'function') {
          this.onload();
        }
      });
    }

    get src() {
      return this._src;
    }

    async decode() {
      if (!this.complete) {
        throw new Error('Image not loaded');
      }
    }
  }

  class FakeJsPDF {
    constructor(options) {
      this.options = options;
      this.pages = [{
        format: options.format,
        orientation: options.orientation,
        images: [],
      }];
      this.savedAs = null;
      pdfInstances.push(this);
    }

    addPage(format, orientation) {
      this.pages.push({ format, orientation, images: [] });
      return this;
    }

    addImage(image, format, x, y, width, height, alias, compression) {
      const currentPage = this.pages[this.pages.length - 1];
      currentPage.images.push({ image, format, x, y, width, height, alias, compression });
      return this;
    }

    save(name) {
      this.savedAs = name;
    }
  }

  const URLCtor = URL;
  URLCtor.createObjectURL = blob => {
    const objectUrl = `blob:mock-${objectUrlMap.size + 1}`;
    objectUrlMap.set(objectUrl, blob);
    return objectUrl;
  };
  URLCtor.revokeObjectURL = objectUrl => {
    objectUrlMap.delete(objectUrl);
  };

  const sandbox = {
    console,
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
    setImmediate,
    URL: URLCtor,
    Image: FakeImage,
    location: { href: 'https://v.sjtu.edu.cn/course/1', hostname: 'v.sjtu.edu.cn' },
    document,
    window: {
      jspdf: { jsPDF: FakeJsPDF },
      _listeners: {},
      addEventListener(type, listener) {
        this._listeners[type] = listener;
      },
      dispatchEvent(type) {
        if (typeof this._listeners[type] === 'function') {
          this._listeners[type]();
        }
      },
      history: {
        pushState() {},
        replaceState() {},
      },
      onurlchange: null,
    },
    MutationObserver: class {
      constructor(callback) {
        this.callback = callback;
      }

      observe() {}

      disconnect() {}
    },
    GM_addStyle() {},
    GM_xmlhttpRequest(details) {
      const response = gmResponses.get(details.url);
      setImmediate(() => {
        if (!response) {
          details.onerror(new Error(`No mock response for ${details.url}`));
          return;
        }

        if (response.type === 'timeout') {
          details.ontimeout();
          return;
        }

        if (response.type === 'error') {
          details.onerror(new Error(response.message || 'mock error'));
          return;
        }

        details.onload({
          status: response.status,
          statusText: response.statusText || 'OK',
          response: response.blob,
          responseText: response.responseText || '',
          finalUrl: response.finalUrl || details.url,
        });
      });
    },
    __SJTU_SLIDE_DOWNLOADER_TEST__: { disableBootstrap: options.disableBootstrap !== false },
  };

  sandbox.globalThis = sandbox;
  sandbox.window.window = sandbox.window;

  return {
    sandbox,
    document,
    gmResponses,
    pdfInstances,
  };
}

function createImageNode({ src = '', currentSrc = '', dataset = {}, complete = true }) {
  const element = new FakeElement('img');
  element.src = src;
  element.currentSrc = currentSrc;
  element.dataset = { ...dataset };
  element.complete = complete;
  return element;
}

async function main() {
  const scriptPath = path.join(__dirname, 'sjtu_slide_downloader.user.js');
  const source = fs.readFileSync(scriptPath, 'utf8');
  const { sandbox, document, gmResponses, pdfInstances } = createSandbox();

  vm.runInNewContext(source, sandbox, { filename: 'sjtu_slide_downloader.user.js' });
  const hooks = sandbox.__SJTU_SLIDE_DOWNLOADER_TEST__;

  assert(typeof hooks.sanitizeFilename === 'function', 'Missing sanitizeFilename hook');
  assert(typeof hooks.collectSlideImageUrls === 'function', 'Missing collectSlideImageUrls hook');
  assert(typeof hooks.generatePDF === 'function', 'Missing generatePDF hook');
  assert(typeof hooks.findBestSlideContainer === 'function', 'Missing findBestSlideContainer hook');
  assert(typeof hooks.isLikelyCoursePage === 'function', 'Missing isLikelyCoursePage hook');
  assert(typeof hooks.checkLocalService === 'function', 'Missing checkLocalService hook');
  assert(typeof hooks.sendJobToLocalService === 'function', 'Missing sendJobToLocalService hook');
  assert(typeof hooks.extractLectureLabel === 'function', 'Missing extractLectureLabel hook');

  assert(
    hooks.sanitizeFilename('课程: 第/1讲?') === '课程 第 1讲',
    'sanitizeFilename should strip reserved filename characters',
  );

  const container = new FakeElement('div');
  container._images = [
    createImageNode({ src: 'https://static.example.com/placeholder.png', dataset: { src: 'https://cdn.example.com/slide-1.png' } }),
    createImageNode({ currentSrc: 'https://cdn.example.com/slide-2.jpg?x=1' }),
    createImageNode({ src: 'https://cdn.example.com/slide-1.png' }),
  ];

  const collected = hooks.collectSlideImageUrls(container);
  assert(collected.length === 2, 'collectSlideImageUrls should deduplicate URLs');
  assert(collected[0] === 'https://cdn.example.com/slide-1.png', 'collectSlideImageUrls should prefer dataset URLs over placeholder src');
  assert(collected[1] === 'https://cdn.example.com/slide-2.jpg?x=1', 'collectSlideImageUrls should capture currentSrc');

  const weakContainer = new FakeElement('div');
  weakContainer._images = [createImageNode({ src: 'https://cdn.example.com/a.png' })];
  weakContainer.children = [1];
  weakContainer.scrollWidth = 200;
  weakContainer.clientWidth = 200;

  const strongContainer = new FakeElement('div');
  strongContainer._images = [
    createImageNode({ src: 'https://cdn.example.com/1.png' }),
    createImageNode({ src: 'https://cdn.example.com/2.png' }),
    createImageNode({ src: 'https://cdn.example.com/3.png' }),
  ];
  strongContainer.children = [1, 2, 3];
  strongContainer.scrollWidth = 1600;
  strongContainer.clientWidth = 400;

  document.setQuerySelectorAll('.ppt-card-wrapper__inner', [weakContainer, strongContainer]);
  assert(hooks.findBestSlideContainer() === strongContainer, 'findBestSlideContainer should prefer the richer scrollable candidate');
  assert(hooks.isLikelyCoursePage() === true, 'isLikelyCoursePage should accept a page with a valid slide container');

  document.setQuerySelectorAll('.ppt-card-wrapper__inner', []);
  document.setQuerySelector('input[placeholder*="PPT"]', new FakeElement('input'));
  assert(hooks.isLikelyCoursePage() === true, 'isLikelyCoursePage should accept a page with PPT-specific markers');

  document.setQuerySelector('input[placeholder*="PPT"]', null);
  sandbox.location.hostname = 'example.com';
  assert(hooks.isLikelyCoursePage() === false, 'isLikelyCoursePage should reject non-SJTU hosts');
  sandbox.location.hostname = 'v.sjtu.edu.cn';
  sandbox.location.href = 'https://v.sjtu.edu.cn/course/2';
  document.setQuerySelectorAll('div, span, li, p, button, h3, h4', [new FakeElement('div')]);
  document.multiResults.set('div, span, li, p, button, h3, h4', [{ textContent: '第10讲 2026-03-16', querySelectorAll() { return []; } }]);
  assert(hooks.extractLectureLabel() === '第10讲', 'extractLectureLabel should capture the lecture number');

  gmResponses.set('http://127.0.0.1:38765/health', {
    status: 200,
    responseText: JSON.stringify({ ok: true, service: 'sjtu-pdf-local-service' }),
  });
  gmResponses.set('http://127.0.0.1:38765/jobs', {
    status: 200,
    responseText: JSON.stringify({
      ok: true,
      page_count: 2,
      pdf_path: 'D:/Downloads/课程 第 1讲.pdf',
    }),
  });
  const healthResult = await hooks.checkLocalService();
  assert(healthResult.ok === true, 'checkLocalService should validate the local service health endpoint');
  const jobResult = await hooks.sendJobToLocalService({ title: '课程: 第/1讲?', imageUrls: ['https://cdn.example.com/1.jpg'] });
  assert(jobResult.ok === true && jobResult.page_count === 2, 'sendJobToLocalService should parse a successful local job response');

  gmResponses.set('https://cdn.example.com/slide-1.png', {
    status: 200,
    blob: { type: 'image/png', width: 1200, height: 900 },
  });
  gmResponses.set('https://cdn.example.com/slide-2.jpg', {
    status: 403,
    blob: { type: 'text/plain', width: 0, height: 0 },
  });
  gmResponses.set('https://cdn.example.com/slide-3.jpg', {
    status: 200,
    blob: { type: 'image/jpeg', width: 1920, height: 1080 },
  });

  const result = await hooks.generatePDF([
    'https://cdn.example.com/slide-1.png',
    'https://cdn.example.com/slide-2.jpg',
    'https://cdn.example.com/slide-3.jpg',
  ], '课程: 第/1讲?');

  assert(result.successCount === 2, 'generatePDF should count successful pages');
  assert(result.failureCount === 1, 'generatePDF should count failed pages');
  assert(result.failedPages.length === 1 && result.failedPages[0].pageNumber === 2, 'generatePDF should report the failed page number');
  assert(pdfInstances.length === 1, 'generatePDF should create one jsPDF instance');
  assert(pdfInstances[0].options.hotfixes.includes('px_scaling'), 'generatePDF should enable the px_scaling hotfix');
  assert(pdfInstances[0].pages.length === 2, 'generatePDF should only add successful pages');
  assert(pdfInstances[0].pages[0].format[0] === 1200 && pdfInstances[0].pages[0].format[1] === 900, 'First page should use the first successful image size');
  assert(pdfInstances[0].pages[1].format[0] === 1920 && pdfInstances[0].pages[1].format[1] === 1080, 'Subsequent pages should use each image size');
  assert(pdfInstances[0].savedAs === '课程 第 1讲.pdf', 'generatePDF should save with a sanitized file name');

  const boot = createSandbox({ disableBootstrap: false });
  const bootContainer = new FakeElement('div');
  bootContainer._images = [createImageNode({ src: 'https://cdn.example.com/1.png' })];
  bootContainer.children = [1];
  bootContainer.scrollWidth = 1600;
  bootContainer.clientWidth = 400;
  boot.document.setQuerySelectorAll('.ppt-card-wrapper__inner', [bootContainer]);
  vm.runInNewContext(source, boot.sandbox, { filename: 'sjtu_slide_downloader.user.js' });
  await new Promise(resolve => setTimeout(resolve, 20));

  assert(typeof boot.sandbox.window._listeners.urlchange === 'function', 'bootstrap should register a urlchange listener when supported');
  assert(boot.document.getElementById('sjtu-pdf-btn'), 'bootstrap should inject the button on a matching page');

  console.log('selfcheck passed');
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
