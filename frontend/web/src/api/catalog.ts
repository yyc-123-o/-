import { api } from "./client";

export interface CourseCatalogConcept {
  id: string;
  title: string;
  title_en?: string;
  summary: string;
  difficulty: number;
  chapter_id: string;
  section_id: string;
  order: number;
  required: boolean;
  prerequisites: string[];
}

export interface CourseCatalogChapter {
  id: string;
  order: number;
  title: string;
  subtitle: string;
  core: boolean;
  sections: Array<{ id: string; order: number; title: string }>;
}

export interface CourseCatalog {
  version: string;
  course: { id: string; title: string; audience: string };
  chapters: CourseCatalogChapter[];
  concepts: CourseCatalogConcept[];
  relations: Array<{ source: string; target: string; kind: string; min_mastery?: number | null }>;
}

export const catalogApi = {
  get: () => api.get<CourseCatalog>("/api/v1/course-catalog").then((response) => response.data),
};
