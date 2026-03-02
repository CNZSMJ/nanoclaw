#!/usr/bin/env npx tsx
/**
 * X Integration - Search Tweets
 * Usage: echo '{"query":"from:elonmusk AI"}' | npx tsx search.ts
 */

import { getBrowserContext, runScript, config, ScriptResult } from '../lib/browser.js';

interface SearchInput {
    query: string;
}

async function searchTweets(input: SearchInput): Promise<ScriptResult> {
    const { query } = input;

    if (!query || query.trim().length === 0) {
        return { success: false, message: 'Search query cannot be empty' };
    }

    let context = null;
    try {
        context = await getBrowserContext();
        const page = context.pages()[0] || await context.newPage();

        const searchUrl = `https://x.com/search?q=${encodeURIComponent(query)}&src=typed_query`;
        await page.goto(searchUrl, { timeout: config.timeouts.navigation, waitUntil: 'domcontentloaded' });

        // Wait for either tweets to load or "no results" message
        try {
            await Promise.race([
                page.waitForSelector('article[data-testid="tweet"]', { timeout: config.timeouts.elementWait }),
                page.waitForSelector('[data-testid="emptyState"]', { timeout: config.timeouts.elementWait })
            ]);
        } catch (e) {
            // Timeout, maybe just slow to load
            await page.waitForTimeout(config.timeouts.pageLoad);
        }

        // Check if we hit login wall
        const isLoginWall = await page.locator('input[autocomplete="username"]').isVisible().catch(() => false);
        if (isLoginWall) {
            return { success: false, message: 'X search restricted. Run /x-integration to re-authenticate or check your account status.' };
        }

        // Scroll a bit to ensure we load a good chunk of actual tweets
        await page.evaluate(() => window.scrollBy(0, 1000));
        await page.waitForTimeout(1000);

        // Extract tweets
        const tweets = await page.evaluate(() => {
            const tweetNodes = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
            return tweetNodes.slice(0, 10).map(node => {
                // Extract author
                const authorEl = node.querySelector('[data-testid="User-Name"]');
                const authorInfo = authorEl ? authorEl.textContent : 'Unknown';

                let handle = '';
                const links = Array.from(authorEl?.querySelectorAll('a') || []);
                const handleLink = links.find(a => a.href.includes('/'))?.getAttribute('href');
                if (handleLink) {
                    handle = handleLink.split('/')[1];
                } else {
                    // Fallback to text parsing
                    const handleMatch = authorInfo?.match(/@(\w+)/);
                    if (handleMatch) handle = handleMatch[1];
                }

                // Extract content
                const textEl = node.querySelector('[data-testid="tweetText"]');
                const text = textEl ? textEl.textContent : '';

                // Extract timestamp
                const timeEl = node.querySelector('time');
                const timestamp = timeEl ? timeEl.getAttribute('datetime') : null;

                // Try to construct URL
                const tweetLinks = Array.from(node.querySelectorAll('a[href*="/status/"]'));
                const tweetUrlPath = tweetLinks.length > 0 ? tweetLinks[0].getAttribute('href') : null;
                const url = tweetUrlPath ? `https://x.com${tweetUrlPath}` : `Unknown URL for user ${handle}`;

                // Get metrics if possible
                const viewsStr = node.querySelector('[aria-label*="View"]')?.getAttribute('aria-label') || '';
                const viewsMatch = viewsStr.match(/([\d,]+|\w+)\s+View/i);
                const views = viewsMatch ? viewsMatch[1] : null;

                const likesStr = node.querySelector('[data-testid="like"]')?.getAttribute('aria-label') || '';
                const likesMatch = likesStr.match(/([\d,]+)\s+Like/i);
                const likes = likesMatch ? likesMatch[1] : null;

                const retweetsStr = node.querySelector('[data-testid="retweet"]')?.getAttribute('aria-label') || '';
                const retweetsMatch = retweetsStr.match(/([\d,]+)\s+Retweet/i);
                const retweets = retweetsMatch ? retweetsMatch[1] : null;

                const repliesStr = node.querySelector('[data-testid="reply"]')?.getAttribute('aria-label') || '';
                const repliesMatch = repliesStr.match(/([\d,]+)\s+Repl/i);
                const replies = repliesMatch ? repliesMatch[1] : null;

                return {
                    author: authorInfo,
                    handle,
                    text,
                    timestamp,
                    url,
                    metrics: {
                        views,
                        likes,
                        retweets,
                        replies
                    }
                };
            }).filter(t => t.text || t.url.includes('/status/'));
        });

        if (tweets.length === 0) {
            const isEmptyState = await page.locator('[data-testid="emptyState"]').isVisible().catch(() => false);
            if (isEmptyState) {
                return { success: true, message: `No results found for query: ${query}`, data: [] };
            }
            return { success: false, message: 'Failed to extract tweets or no tweets rendered. The page layout might have changed or results are empty.' };
        }

        return {
            success: true,
            message: `Found ${tweets.length} tweets for query: ${query}`,
            data: tweets
        };

    } finally {
        if (context) await context.close();
    }
}

runScript<SearchInput>(searchTweets);
