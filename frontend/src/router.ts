import { createRouter, createWebHistory } from "vue-router";
import Dashboard from "./views/Dashboard.vue";
import Experiment from "./views/Experiment.vue";
import ExperimentResult from "./views/ExperimentResult.vue";
import Skills from "./views/Skills.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "dashboard", component: Dashboard },
    { path: "/experiments/:id", name: "experiment", component: Experiment },
    { path: "/experiments/:id/result", name: "experiment-result", component: ExperimentResult },
    { path: "/skills", name: "skills", component: Skills },
  ],
});
