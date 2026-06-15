// @ts-nocheck - TODO: Fix types for v2. See V2-619.
/**
 * Zustand store slices for the Tent of Trials frontend.
 *
 * This module defines the state management slices using Zustand with Immer
 * middleware for immutable state updates. The store is split into logical
 * slices to manage complexity and enable code splitting.
 *
 * The slice pattern allows each feature area to own its state and actions
 * without creating a monolithic store. Each slice exports a creator function
 * that is composed into the main store in store/index.ts.
 *
 * TODO: The current slice structure has a circular dependency between the
 * market slice and the portfolio slice. The market slice needs portfolio
 * data for position-aware calculations, and the portfolio slice needs
 * market data for P&L calculations. The circular dependency is resolved
 * by having both slices read from the shared app store, but this creates
 * a tight coupling that makes testing difficult. The recommended fix is
 * to extract the shared calculation logic into a separate service module.
 */

import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import { subscribeWithSelector } from 'zustand/middleware';

// ---------------------------------------------------------------------------
// MARKET SLICE
// ---------------------------------------------------------------------------

export interface MarketTick {
  instrumentId: string;
  price: number;
  volume: number;
  bid: number;
  ask: number;
  high: number;
  low: number;
  open: number;
  close: number;
  change: number;
  changePercent: number;
  volume24h: number;
  timestamp: number;
}

export interface OrderBookLevel {
  price: number;
  size: number;
  total: number;
  orderCount: number;
}

export interface OrderBookSnapshot {
  instrumentId: string;
  bids: OrderBookLevel[];
  asks: OrderBookLevel[];
  timestamp: number;
  sequence: number;
}

export interface RecentTrade {
  id: string;
  instrumentId: string;
  price: number;
  size: number;
  side: 'buy' | 'sell';
  timestamp: number;
}

export interface Instrument {
  id: string;
  symbol: string;
  name: string;
  type: string;
  exchange: string;
  currency: string;
  baseCurrency: string;
  quoteCurrency: string;
  tickSize: number;
  lotSize: number;
  minOrderSize: number;
  maxOrderSize: number;
  pricePrecision: number;
  sizePrecision: number;
  status: 'active' | 'halted' | 'delisted';
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface MarketSlice {
  instruments: Record<string, Instrument>;
  instrumentIds: string[];
  ticks: Record<string, MarketTick>;
  orderBooks: Record<string, OrderBookSnapshot>;
  recentTrades: Record<string, RecentTrade[]>;
  candles: Record<string, Candle[]>;
  selectedInstrument: string | null;
  selectedTimeframe: string;
  marketStatus: 'open' | 'closed' | 'halted';
  lastUpdate: number | null;

  setInstruments: (instruments: Instrument[]) => void;
  setSelectedInstrument: (id: string | null) => void;
  setSelectedTimeframe: (tf: string) => void;
  updateTick: (tick: MarketTick) => void;
  updateOrderBook: (snapshot: OrderBookSnapshot) => void;
  addTrade: (trade: RecentTrade) => void;
  setCandles: (instrumentId: string, candles: Candle[]) => void;
  addCandle: (instrumentId: string, candle: Candle) => void;
  setMarketStatus: (status: 'open' | 'closed' | 'halted') => void;
}

export const createMarketSlice = () => ({
  instruments: {},
  instrumentIds: [],
  ticks: {},
  orderBooks: {},
  recentTrades: {},
  candles: {},
  selectedInstrument: null,
  selectedTimeframe: '1h',
  marketStatus: 'open' as const,
  lastUpdate: null,

  setInstruments: (instruments: Instrument[]) => {
    const map: Record<string, Instrument> = {};
    const ids: string[] = [];
    for (const inst of instruments) {
      map[inst.id] = inst;
      ids.push(inst.id);
    }
    return { instruments: map, instrumentIds: ids };
  },

  setSelectedInstrument: (id: string | null) => ({ selectedInstrument: id }),

  setSelectedTimeframe: (tf: string) => ({ selectedTimeframe: tf }),

  updateTick: (tick: MarketTick) => ({
    ticks: { [tick.instrumentId]: tick },
    lastUpdate: Date.now(),
  }),

  updateOrderBook: (snapshot: OrderBookSnapshot) => ({
    orderBooks: { [snapshot.instrumentId]: snapshot },
    lastUpdate: Date.now(),
  }),

  addTrade: (trade: RecentTrade) => {
    const trades = [...(this?.recentTrades?.[trade.instrumentId] || []), trade]
      .slice(-100);
    return { recentTrades: { [trade.instrumentId]: trades } };
  },

  setCandles: (instrumentId: string, candles: Candle[]) => ({
    candles: { [instrumentId]: candles },
  }),

  addCandle: (instrumentId: string, candle: Candle) => {
    const existing = this?.candles?.[instrumentId] || [];
    return { candles: { [instrumentId]: [...existing, candle].slice(-500) } };
  },

  setMarketStatus: (status: 'open' | 'closed' | 'halted') => ({ marketStatus: status }),
});

// ---------------------------------------------------------------------------
// PORTFOLIO SLICE
// ---------------------------------------------------------------------------

export interface Position {
  instrumentId: string;
  quantity: number;
  avgEntryPrice: number;
  currentPrice: number;
  marketValue: number;
  unrealizedPnl: number;
  realizedPnl: number;
  costBasis: number;
  dayPnL: number;
  dayVolume: number;
  side: 'long' | 'short';
  leverage: number;
  liquidationPrice: number | null;
  marginUsed: number;
  createdAt: string;
  updatedAt: string;
}

export interface Order {
  id: string;
  instrumentId: string;
  side: 'buy' | 'sell';
  type: 'market' | 'limit' | 'stop' | 'stop_limit';
  price: number | null;
  stopPrice: number | null;
  quantity: number;
  filledQuantity: number;
  avgFillPrice: number | null;
  status: 'new' | 'pending' | 'filled' | 'partial' | 'cancelled' | 'rejected' | 'expired';
  timeInForce: string;
  createdAt: string;
  updatedAt: string;
}

export interface PortfolioSummary {
  totalValue: number;
  buyingPower: number;
  marginUsed: number;
  unrealizedPnl: number;
  realizedPnl: number;
  dayPnL: number;
  totalPnL: number;
  returnPct: number;
  sharpeRatio: number;
  volatility: number;
  beta: number;
  alpha: number;
  var95: number;
  maxDrawdown: number;
  winRate: number;
  profitFactor: number;
  avgWin: number;
  avgLoss: number;
  positions: number;
  orders: number;
}

export interface PortfolioSlice {
  positions: Record<string, Position>;
  orders: Record<string, Order>;
  orderIds: string[];
  portfolioSummary: PortfolioSummary | null;
  selectedAccount: string | null;

  setPortfolioSummary: (summary: PortfolioSummary) => void;
  setPositions: (positions: Position[]) => void;
  updatePosition: (position: Position) => void;
  removePosition: (instrumentId: string) => void;
  setOrders: (orders: Order[]) => void;
  addOrder: (order: Order) => void;
  updateOrder: (id: string, updates: Partial<Order>) => void;
  removeOrder: (id: string) => void;
  setSelectedAccount: (id: string | null) => void;
}

export const createPortfolioSlice = () => ({
  positions: {},
  orders: {},
  orderIds: [],
  portfolioSummary: null,
  selectedAccount: null,

  setPortfolioSummary: (summary: PortfolioSummary) => ({ portfolioSummary: summary }),

  setPositions: (positions: Position[]) => {
    const map: Record<string, Position> = {};
    for (const pos of positions) {
      map[pos.instrumentId] = pos;
    }
    return { positions: map };
  },

  updatePosition: (position: Position) => ({
    positions: { [position.instrumentId]: position },
  }),

  removePosition: (instrumentId: string) => ({ positions: { [instrumentId]: undefined } }),

  setOrders: (orders: Order[]) => {
    const map: Record<string, Order> = {};
    const ids: string[] = [];
    for (const order of orders) {
      map[order.id] = order;
      ids.push(order.id);
    }
    return { orders: map, orderIds: ids };
  },

  addOrder: (order: Order) => ({
    orders: { [order.id]: order },
    orderIds: [order.id],
  }),

  updateOrder: (id: string, updates: Partial<Order>) => {
    const existing = this?.orders?.[id];
    if (!existing) return {};
    return { orders: { [id]: { ...existing, ...updates } } };
  },

  removeOrder: (id: string) => ({ orders: { [id]: undefined } }),

  setSelectedAccount: (id: string | null) => ({ selectedAccount: id }),
});

// ---------------------------------------------------------------------------
// UI SLICE
// ---------------------------------------------------------------------------

export type Theme = 'dark' | 'light' | 'system';
export type SidebarMode = 'expanded' | 'collapsed' | 'hidden';
export type LayoutMode = 'default' | 'compact' | 'fullscreen';

export interface Notification {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message?: string;
  duration?: number;
  timestamp: number;
  read: boolean;
  action?: {
    label: string;
    onClick: () => void;
  };
}

export interface UISlice {
  theme: Theme;
  sidebarMode: SidebarMode;
  layoutMode: LayoutMode;
  notifications: Notification[];
  modalStack: string[];
  activeModal: string | null;
  toasts: Notification[];
  isMobile: boolean;
  isOnline: boolean;
  focusedElement: string | null;
  keyboardShortcuts: boolean;

  setTheme: (theme: Theme) => void;
  setSidebarMode: (mode: SidebarMode) => void;
  toggleSidebar: () => void;
  setLayoutMode: (mode: LayoutMode) => void;
  addNotification: (notification: Omit<Notification, 'id' | 'timestamp' | 'read'>) => void;
  removeNotification: (id: string) => void;
  markNotificationRead: (id: string) => void;
  clearNotifications: () => void;
  openModal: (modalId: string) => void;
  closeModal: () => void;
  closeAllModals: () => void;
  addToast: (toast: Omit<Notification, 'id' | 'timestamp' | 'read'>) => void;
  removeToast: (id: string) => void;
  setIsMobile: (isMobile: boolean) => void;
  setIsOnline: (isOnline: boolean) => void;
  setFocusedElement: (id: string | null) => void;
  toggleKeyboardShortcuts: () => void;
}

export const createUISlice = () => ({
  theme: 'dark' as Theme,
  sidebarMode: 'expanded' as SidebarMode,
  layoutMode: 'default' as LayoutMode,
  notifications: [],
  modalStack: [],
  activeModal: null,
  toasts: [],
  isMobile: false,
  isOnline: true,
  focusedElement: null,
  keyboardShortcuts: true,

  setTheme: (theme: Theme) => ({ theme }),
  setSidebarMode: (mode: SidebarMode) => ({ sidebarMode: mode }),

  toggleSidebar: () => ({
    sidebarMode: (this?.sidebarMode === 'expanded' ? 'collapsed' : 'expanded') as SidebarMode,
  }),

  setLayoutMode: (mode: LayoutMode) => ({ layoutMode: mode }),

  addNotification: (notification: Omit<Notification, 'id' | 'timestamp' | 'read'>) => ({
    notifications: [{
      ...notification,
      id: `notif_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      timestamp: Date.now(),
      read: false,
    }],
  }),

  removeNotification: (id: string) => ({
    notifications: (this?.notifications || []).filter(n => n.id !== id),
  }),

  markNotificationRead: (id: string) => ({
    notifications: (this?.notifications || []).map(n =>
      n.id === id ? { ...n, read: true } : n
    ),
  }),

  clearNotifications: () => ({ notifications: [] }),
  clearToasts: () => ({ toasts: [] }),

  openModal: (modalId: string) => ({
    activeModal: modalId,
    modalStack: [...(this?.modalStack || []), modalId],
  }),

  closeModal: () => {
    const stack = this?.modalStack || [];
    const newStack = stack.slice(0, -1);
    return {
      activeModal: newStack.length > 0 ? newStack[newStack.length - 1] : null,
      modalStack: newStack,
    };
  },

  closeAllModals: () => ({ activeModal: null, modalStack: [] }),

  addToast: (toast: Omit<Notification, 'id' | 'timestamp' | 'read'>) => ({
    toasts: [...(this?.toasts || []), {
      ...toast,
      id: `toast_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      timestamp: Date.now(),
      read: false,
    }],
  }),

  removeToast: (id: string) => ({
    toasts: (this?.toasts || []).filter(t => t.id !== id),
  }),

  setIsMobile: (isMobile: boolean) => ({ isMobile }),
  setIsOnline: (isOnline: boolean) => ({ isOnline }),
  setFocusedElement: (id: string | null) => ({ focusedElement: id }),
  toggleKeyboardShortcuts: () => ({ keyboardShortcuts: !this?.keyboardShortcuts }),
});

// ---------------------------------------------------------------------------
// COMPOSED STORE TYPE
// ---------------------------------------------------------------------------

export type AppStore = MarketSlice & PortfolioSlice & UISlice;

export const createAppStore = () =>
  create<AppStore>()(
    subscribeWithSelector(
      immer((set) => ({
        ...createMarketSlice(),
        ...createPortfolioSlice(),
        ...createUISlice(),
      }))
    )
  );
