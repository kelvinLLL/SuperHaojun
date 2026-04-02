import "dotenv/config";
// Required for custom proxy endpoints with self-signed or CDN-issued certificates
process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";
import { createInterface } from "node:readline";
import { Agent } from "@mariozechner/pi-agent-core";
import { streamSimple } from "@mariozechner/pi-ai";
import "@mariozechner/pi-ai/openai-completions";
import { loadModelConfig, createModel } from "./config.js";
import type { AgentEvent } from "@mariozechner/pi-agent-core";

const SYSTEM_PROMPT = `You are SuperHaojun, a highly capable AI coding assistant.
You help with programming tasks, code review, architecture design, and debugging.
Be concise and direct. Respond in the same language the user uses.`;

async function main() {
  const config = loadModelConfig();
  const model = createModel(config);

  console.log(`\n🤖 SuperHaojun Agent`);
  console.log(`   Model: ${config.modelId} @ ${config.baseUrl}`);
  console.log(`   Type your message, press Enter to send. Ctrl+C to exit.\n`);

  const agent = new Agent({
    initialState: {
      systemPrompt: SYSTEM_PROMPT,
      model,
      thinkingLevel: "off",
      tools: [],
    },
    streamFn: (streamModel, context, options) => {
      return streamSimple(streamModel, context, {
        ...options,
        apiKey: config.apiKey,
      });
    },
  });

  // Subscribe to events for streaming output
  let isFirstTextDelta = true;
  agent.subscribe((event: AgentEvent) => {
    switch (event.type) {
      case "message_start":
        if (event.message.role === "assistant") {
          isFirstTextDelta = true;
        }
        break;

      case "message_update":
        if (event.assistantMessageEvent.type === "text_delta") {
          if (isFirstTextDelta) {
            process.stdout.write("\n\x1b[36m"); // cyan color
            isFirstTextDelta = false;
          }
          process.stdout.write(event.assistantMessageEvent.delta);
        }
        break;

      case "message_end":
        if (event.message.role === "assistant") {
          process.stdout.write("\x1b[0m\n\n"); // reset color
          if (event.message.errorMessage) {
            console.error(`\x1b[31mError: ${event.message.errorMessage}\x1b[0m\n`);
          }
        }
        break;

      case "agent_end":
        // Turn complete — ready for next input
        break;
    }
  });

  const rl = createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  rl.on("close", () => {
    console.log("\nBye!");
    process.exit(0);
  });

  const prompt = () => {
    rl.question("\x1b[33myou>\x1b[0m ", async (input) => {
      const trimmed = input.trim();
      if (!trimmed) {
        prompt();
        return;
      }

      if (trimmed === "/quit" || trimmed === "/exit") {
        console.log("Bye!");
        rl.close();
        process.exit(0);
      }

      if (trimmed === "/clear") {
        agent.reset();
        console.log("Conversation cleared.\n");
        prompt();
        return;
      }

      if (trimmed === "/messages") {
        console.log(`Messages in context: ${agent.state.messages.length}\n`);
        prompt();
        return;
      }

      try {
        await agent.prompt(trimmed);
      } catch (err) {
        console.error(`\x1b[31mError: ${err instanceof Error ? err.message : String(err)}\x1b[0m\n`);
      }

      prompt();
    });
  };

  prompt();
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
