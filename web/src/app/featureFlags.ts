const envValue = (import.meta.env.VITE_FEATURE_TOPIC_INSIGHTS ?? "").toString().toLowerCase();

export const featureFlags = {
  topicInsights: envValue ? envValue !== "false" && envValue !== "0" : true,
};
