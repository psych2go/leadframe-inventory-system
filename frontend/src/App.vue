<template>
  <router-view v-slot="{ Component }">
    <keep-alive include="InventoryList">
      <component :is="Component" />
    </keep-alive>
  </router-view>
</template>

<style>
:root {
  --lf-bg: #f3f6f7;
  --lf-surface: #ffffff;
  --lf-surface-muted: #eaf0f1;
  --lf-text: #17343b;
  --lf-text-muted: #708187;
  --lf-border: #d9e2e4;
  --lf-primary: #0f7b78;
  --lf-primary-dark: #0a5f5d;
  --lf-in: #2f9e68;
  --lf-out: #d9544d;
  --lf-warning: #c98218;
  --lf-data-font: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  --van-primary-color: var(--lf-primary);
  --van-success-color: var(--lf-in);
  --van-danger-color: var(--lf-out);
  --van-warning-color: var(--lf-warning);
  --van-text-color: var(--lf-text);
  --van-text-color-2: var(--lf-text-muted);
  --van-background: var(--lf-bg);
  --van-background-2: var(--lf-surface);
  --van-border-color: var(--lf-border);
  --van-radius-md: 6px;
  --van-radius-lg: 8px;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html {
  background: var(--lf-bg);
}

body {
  font-family: Inter, "PingFang SC", "Microsoft YaHei", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  color: var(--lf-text);
  background: var(--lf-bg);
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
}

button,
input,
textarea {
  font: inherit;
}

.van-nav-bar {
  background: rgba(255, 255, 255, 0.96);
  border-bottom: 1px solid var(--lf-border);
  box-shadow: none;
}

.van-nav-bar::after {
  display: none;
}

.van-nav-bar__title {
  color: var(--lf-text);
  font-size: 16px;
  font-weight: 700;
}

.van-nav-bar .van-icon {
  color: var(--lf-primary);
}

.van-cell-group {
  overflow: hidden;
  border: 1px solid var(--lf-border);
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(23, 52, 59, 0.04);
}

.van-cell-group__title {
  padding: 18px 16px 8px;
  color: var(--lf-text-muted);
  font-size: 12px;
  font-weight: 700;
}

.van-field__label {
  color: #466067;
}

.van-field__control,
.van-cell__value {
  color: var(--lf-text);
}

.van-button {
  border-radius: 6px;
  font-weight: 650;
}

.van-button--large {
  height: 48px;
}

.van-popup--bottom {
  border-radius: 8px 8px 0 0;
}

.van-tag {
  border-radius: 4px;
}

:is(
  .stock-in-page,
  .stock-out-page,
  .detail-page,
  .edit-page,
  .grouped-detail,
  .audit-page
) {
  min-height: 100vh;
  background: var(--lf-bg);
}

:is(.stock-in-page, .detail-page, .edit-page) > .van-cell-group {
  margin: 12px;
}

:is(.stock-in-page, .stock-out-page, .detail-page, .edit-page) .submit-bar,
.detail-page .actions {
  padding: 12px;
}

@media (min-width: 760px) {
  #app {
    width: 100%;
    max-width: 760px;
    min-height: 100vh;
    margin: 0 auto;
    border-right: 1px solid var(--lf-border);
    border-left: 1px solid var(--lf-border);
    background: var(--lf-bg);
  }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
  }
}
</style>
