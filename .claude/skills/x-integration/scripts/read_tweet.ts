#!/usr/bin/env npx tsx
/**
 * X Integration - Read Tweet & Replies
 * Usage: echo '{"tweetUrl":"https://x.com/elonmusk/status/123"}' | npx tsx read_tweet.ts
 */

import { getBrowserContext, navigateToTweet, runScript, config, ScriptResult } from '../lib/browser.js';

interface ReadInput {
    tweetUrl: string;
}

async function readTweet(input: ReadInput): Promise<ScriptResult> {
    const { tweetUrl } = input;

    if (!tweetUrl) {
        return { success: false, message: 'Tweet URL cannot be empty' };
    }

    let context = null;
    try {
        context = await getBrowserContext();
        const navResult = await navigateToTweet(context, tweetUrl);

        if (!navResult.success) {
            return { success: false, message: navResult.error || 'Failed to navigate to tweet' };
        }

        const page = navResult.page;

        // Check if we hit login wall
        const isLoginWall = await page.locator('input[autocomplete="username"]').isVisible().catch(() => false);
        if (isLoginWall) {
            return { success: false, message: 'X restricted access to this tweet. Run /x-integration to re-authenticate or check your account status.' };
        }

        // Scroll a bit to load replies
        await page.evaluate(() => window.scrollBy(0, 800));
        await page.waitForTimeout(1000);

        const threadData = await page.evaluate(() => {
            const articleNodes = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
            if (articleNodes.length === 0) return null;

            const parseArticle = (node: Element) => {
                const authorEl = node.querySelector('[data-testid="User-Name"]');
                const authorInfo = authorEl ? authorEl.textContent : 'Unknown';

                let handle = '';
                const links = Array.from(authorEl?.querySelectorAll('a') || []);
                const handleLink = links.find(a => a.href.includes('/'))?.getAttribute('href');
                if (handleLink) {
                    handle = handleLink.split('/')[1];
                } else {
                    const handleMatch = authorInfo?.match(/@(\w+)/);
                    if (handleMatch) handle = handleMatch[1];
                }

                const textEl = node.querySelector('[data-testid="tweetText"]');
                const text = textEl ? textEl.innerHTML.replace(/<br>/g, '\n').replace(/<[^>]*>?/gm, '') : '';

                const timeEl = node.querySelector('time');
                const timestamp = timeEl ? timeEl.getAttribute('datetime') : null;

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
                    metrics: { views, likes, retweets, replies }
                };
            };

            // The first article is typically the main tweet we navigated to (or part of the thread above it)
            // More robust: Find the specific tweet by URL structure from data-testid="User-Name" links
            // But for simplicity, we assume the first large one is main, or we just return the array
            return articleNodes.map(parseArticle).filter(t => t.text.length > 0);
        });

        if (!threadData || threadData.length === 0) {
            return { success: false, message: 'Failed to extract tweet content. The page layout might have changed or results are empty.' };
        }

        return {
            success: true,
            message: `Successfully read tweet and ${threadData.length - 1} replies.`,
            data: {
                main_tweet: threadData[0],
                context_or_replies: threadData.slice(1)
            }
        };

    } finally {
        if (context) await context.close();
    }
}

runScript<ReadInput>(readTweet);
