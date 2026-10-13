import { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import LivePriceWidget from './LivePriceWidget';

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

const pricePayload = {
  count: 2,
  avg: 42,
  min: 10,
  max: 80,
  listings: [],
};

function setupObserver() {
  let callback;
  const instances = [];
  class MockObserver {
    constructor(cb, options) {
      this.callback = cb;
      this.options = options;
      this.observe = jest.fn();
      this.disconnect = jest.fn();
      callback = cb;
      instances.push(this);
    }
  }
  global.IntersectionObserver = MockObserver;
  return {
    instances,
    intersect() {
      callback([{ isIntersecting: true }]);
    },
  };
}

function renderWidget() {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(<LivePriceWidget query="Prizm Basketball" label="Live eBay" />);
  });
  return {
    container,
    unmount() {
      act(() => root.unmount());
      container.remove();
    },
  };
}

describe('LivePriceWidget lazy loading', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    axios.get.mockReset();
  });

  afterEach(() => {
    jest.useRealTimers();
    document.body.innerHTML = '';
  });

  test('uses an 800px root margin and waits for intersection', async () => {
    const observer = setupObserver();
    axios.get.mockResolvedValue({ data: pricePayload });
    const view = renderWidget();

    expect(observer.instances[0].options.rootMargin).toBe('800px');
    expect(axios.get).not.toHaveBeenCalled();

    await act(async () => {
      observer.intersect();
    });

    expect(axios.get).toHaveBeenCalledTimes(1);
    expect(axios.get).toHaveBeenCalledWith(
      expect.stringContaining('/packs/price'),
      { params: { q: 'Prizm Basketball', refresh: false } },
    );
    expect(view.container.textContent).toContain('$42');
    view.unmount();
  });

  test('fetches after 3 seconds when the observer never fires', async () => {
    setupObserver();
    axios.get.mockResolvedValue({ data: pricePayload });
    const view = renderWidget();

    await act(async () => {
      jest.advanceTimersByTime(2999);
    });
    expect(axios.get).not.toHaveBeenCalled();

    await act(async () => {
      jest.advanceTimersByTime(1);
    });

    expect(axios.get).toHaveBeenCalledTimes(1);
    expect(view.container.textContent).toContain('$42');
    view.unmount();
  });

  test('retries a failed fetch once', async () => {
    const observer = setupObserver();
    axios.get
      .mockRejectedValueOnce({ response: { data: { detail: 'temporarily down' } } })
      .mockResolvedValueOnce({ data: pricePayload });
    const view = renderWidget();

    await act(async () => {
      observer.intersect();
    });

    expect(axios.get).toHaveBeenCalledTimes(2);
    expect(view.container.textContent).toContain('$42');
    expect(view.container.textContent).not.toContain('temporarily down');
    view.unmount();
  });

  test('stops after the single retry fails', async () => {
    const observer = setupObserver();
    axios.get.mockRejectedValue({ response: { data: { detail: 'price check unavailable' } } });
    const view = renderWidget();

    await act(async () => {
      observer.intersect();
    });

    expect(axios.get).toHaveBeenCalledTimes(2);
    expect(view.container.textContent).toContain('price check unavailable');
    view.unmount();
  });
});
