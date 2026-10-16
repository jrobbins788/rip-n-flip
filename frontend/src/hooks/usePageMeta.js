import { useEffect } from 'react';

const SITE = 'https://www.ripnflipapp.com';

function setTag(selector, create, attr, value) {
  let el = document.head.querySelector(selector);
  if (!el) {
    el = create();
    document.head.appendChild(el);
  }
  el.setAttribute(attr, value);
}

function meta(key, keyAttr, content) {
  setTag(`meta[${keyAttr}="${key}"]`, () => {
    const m = document.createElement('meta');
    m.setAttribute(keyAttr, key);
    return m;
  }, 'content', content);
}

// Sets per-page title, description, canonical and og/twitter text tags.
export default function usePageMeta({ title, description, path }) {
  useEffect(() => {
    const url = SITE + path;
    document.title = title;
    meta('description', 'name', description);
    meta('og:title', 'property', title);
    meta('og:description', 'property', description);
    meta('og:url', 'property', url);
    meta('twitter:title', 'name', title);
    meta('twitter:description', 'name', description);
    setTag('link[rel="canonical"]', () => {
      const l = document.createElement('link');
      l.setAttribute('rel', 'canonical');
      return l;
    }, 'href', url);
  }, [title, description, path]);
}
