# frozen_string_literal: true

require "cgi"

class TaxonomyPage < Jekyll::PageWithoutAFile
  def initialize(site, type, slug, name, posts)
    decoded_slug = CGI.unescape(slug)
    super(site, site.source, File.join(type, decoded_slug), "index.html")
    self.content = ""
    self.data = {
      "layout" => "archive",
      "title" => name,
      "taxonomy_type" => type,
      "taxonomy_slug" => slug,
      "posts" => posts
    }
  end
end

class TaxonomyGenerator < Jekyll::Generator
  safe true

  def generate(site)
    {
      "category" => ["categories", "category_slugs"],
      "tag" => ["tags", "tag_slugs"]
    }.each do |type, (names_key, slugs_key)|
      groups = {}
      site.posts.docs.each do |post|
        names = Array(post.data[names_key])
        slugs = Array(post.data[slugs_key])
        names.each_with_index do |name, index|
          slug = slugs[index] || Jekyll::Utils.slugify(name)
          groups[slug] ||= { "name" => name, "posts" => [] }
          groups[slug]["posts"] << post
        end
      end
      if type == "category"
        Array(site.config["menu_categories"]).each do |item|
          groups[item["slug"]] ||= { "name" => item["name"], "posts" => [] }
        end
      end
      groups.each do |slug, group|
        site.pages << TaxonomyPage.new(
          site, type, slug, group["name"], group["posts"]
        )
      end
    end
  end
end
