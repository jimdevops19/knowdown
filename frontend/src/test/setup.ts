import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Vitest globals are off (tests import what they use), which also turns off
// Testing Library's automatic teardown — so unmount between tests by hand, or
// the second render finds two copies of the component in the document.
afterEach(cleanup)
